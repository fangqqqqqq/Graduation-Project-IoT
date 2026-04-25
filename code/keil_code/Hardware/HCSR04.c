#include "stm32f10x.h"                  
#include "Delay.h"
#include "SmartCar.h"
#include "OLED.h"
#include "Servo.h" 
#include "Buzzer.h"

int16_t CountNum;

void HCSR04_Init(void)
{
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_TIM1, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    
    GPIO_InitTypeDef GPIO_InitStructure;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP; 
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_14; 
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
    
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPD;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_15; 
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
    
    TIM_InternalClockConfig(TIM1);
    TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
    TIM_TimeBaseInitStructure.TIM_ClockDivision = TIM_CKD_DIV1;
    TIM_TimeBaseInitStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInitStructure.TIM_Period = 60000 - 1;
    TIM_TimeBaseInitStructure.TIM_Prescaler = 72 - 1; 
    TIM_TimeBaseInitStructure.TIM_RepetitionCounter = 0;
    TIM_TimeBaseInit(TIM1, &TIM_TimeBaseInitStructure);
}

float HCSR04_Distance(void)
{
    float Distance = 0;
    GPIO_ResetBits(GPIOB, GPIO_Pin_14);
    GPIO_SetBits(GPIOB, GPIO_Pin_14);
    Delay_us(40);
    GPIO_ResetBits(GPIOB, GPIO_Pin_14);
    
    while(GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_15) == RESET);
    TIM1->CNT = 0;
    TIM_Cmd(TIM1, ENABLE);
    while(GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_15) == SET);
    TIM_Cmd(TIM1, DISABLE);
    
    CountNum = TIM_GetCounter(TIM1);
    Distance = (CountNum * 1.0 * 0.034) / 2;
    Delay_ms(30); 
    return Distance;
}

// ?? “大跨步” 步进扫描避障逻辑 ??
void AvoidObstacle(void)
{
    uint8_t i;
    float temp_dist;

    // 1. 触发避障，停车报警
    Car_Stop(); 
    Buzzer();
    Delay_ms(200); 

    // 2. === 向左大跨步扫描 (只扫4次) ===
    for(i = 0; i < 4; i++)
    {
        // 2.1 向左转一大步
        CounterClockwise_Rotation(); 
        Delay_ms(350); // ?? 加大步长：从120ms改成350ms (约30-45度)
        Car_Stop();
        Delay_ms(200); // 停稳等待
        
        // 2.2 看一眼
        temp_dist = HCSR04_Distance();
        OLED_ShowNum(2, 1, temp_dist, 3); 
        
        // 2.3 有路吗？
        if(temp_dist > 25.0)
        {
            Move_Forward(); // 找到了，直接走
            return;         
        }
    }
    
    // === 左边4次都没路，大回环去右边 ===
    
    // 3. 先把头甩到右边去
    // 因为刚才向左大概转了 4*350 = 1400ms 的量
    // 所以要回转 > 1400ms 才能看到右边，这里给 1800ms
    Clockwise_Rotation(); 
    Delay_ms(1800); 
    Car_Stop();
    Delay_ms(200);
    
    // 4. === 向右大跨步扫描 (只扫4次) ===
    for(i = 0; i < 4; i++)
    {
        Clockwise_Rotation(); // 向右一大步
        Delay_ms(350);
        Car_Stop();
        Delay_ms(200);
        
        temp_dist = HCSR04_Distance();
        OLED_ShowNum(2, 1, temp_dist, 3);
        
        if(temp_dist > 25.0)
        {
            Move_Forward();
            return; 
        }
    }

    // 5. 还是没路 -> 彻底被困
    Car_Stop();
    while(1)
    {
        Buzzer(); 
        Delay_ms(500);
    }
}

void Following(void)
{
    float a = HCSR04_Distance();
    if(a < 20) Move_Backward();
    else if(a > 20 && a < 40) Car_Stop();
    else Move_Forward();
}