#include "SoftSerial.h"

// 定义接收缓冲区
char GPS_Buffer[512];
uint16_t GPS_Index = 0;

void SoftSerial_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStructure;
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
    NVIC_InitTypeDef NVIC_InitStructure;

    // 1. 开启 GPIOB 和 TIM4 的时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4, ENABLE); // 借用 TIM4 做心脏

    // 2. 配置 PB7 为上拉输入 (用作模拟 RX，监听 GPS)
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    // 3. 配置 PB6 为推挽输出 (用作模拟 TX，虽然现在不发指令，但留着备用)
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
    GPIO_SetBits(GPIOB, GPIO_Pin_6); // TX 默认保持高电平

    // 4. 配置 TIM4 定时器 (3倍过采样)
    // 72MHz / 72 = 1MHz (1微秒跳动一下)
    // Period 设为 34，也就是每 35 微秒触发一次中断 (28800 Hz)
    TIM_TimeBaseStructure.TIM_Period = 35 - 1; 
    TIM_TimeBaseStructure.TIM_Prescaler = 72 - 1;
    TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1;
    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM4, &TIM_TimeBaseStructure);

    TIM_ITConfig(TIM4, TIM_IT_Update, ENABLE);
    TIM_Cmd(TIM4, ENABLE);

    // 5. 配置定时器中断优先级
    NVIC_InitStructure.NVIC_IRQChannel = TIM4_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

// ==========================================================
// TIM4 中断服务函数：这里的状态机是软件串口的灵魂
// ==========================================================
void TIM4_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM4, TIM_IT_Update) != RESET)
    {
        TIM_ClearITPendingBit(TIM4, TIM_IT_Update); // 清除中断标志位

        static uint8_t rx_state = 0;    // 状态机
        static uint8_t rx_data = 0;     // 拼装中的一个字节
        static uint8_t bit_count = 0;   // 已经读了几个比特
        static uint8_t tick_count = 0;  // 节拍计数器
        
        // 读取 PB7 当前电平
        uint8_t rx_pin = GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_7);
        
        switch (rx_state)
        {
            case 0: // 空闲等待阶段
                if (rx_pin == 0) // 捕捉到下拉的起始位
                {
                    rx_state = 1;
                    tick_count = 0;
                }
                break;
                
            case 1: // 确认起始位阶段 (防干扰杂波)
                tick_count++;
                if (tick_count == 1) // 走到脉冲的中间点去确认
                {
                    if (rx_pin == 0) 
                    {
                        rx_state = 2; // 确实是起始信号，进入接收状态
                        tick_count = 0;
                        bit_count = 0;
                        rx_data = 0;
                    }
                    else 
                    {
                        rx_state = 0; // 假信号，重新等待
                    }
                }
                break;
                
            case 2: // 数据位接收阶段
                tick_count++;
                if (tick_count == 3) // 每过 3 个节拍，刚好是一个比特的宽度
                {
                    tick_count = 0;
                    rx_data >>= 1; // 串口是低位先发，所以每次向右推
                    if (rx_pin == 1) 
                    {
                        rx_data |= 0x80; // 如果读到高电平，把最高位置 1
                    }
                    
                    bit_count++;
                    if (bit_count == 8) // 8位读满，准备收工
                    {
                        rx_state = 3;
                    }
                }
                break;
                
            case 3: // 停止位阶段
                tick_count++;
                if (tick_count == 3)
                {
                    // 完美！组装好了一个字节，丢进缓冲池
                    GPS_Buffer[GPS_Index] = rx_data;
                    GPS_Index++;
                    if (GPS_Index >= 512) 
                    {
                        GPS_Index = 0; // 防止数组爆炸跑飞
                    }
                    rx_state = 0; // 还原状态，等下一个字母
                }
                break;
        }
    }
}
