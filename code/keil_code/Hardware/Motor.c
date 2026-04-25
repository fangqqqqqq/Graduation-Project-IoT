#include "stm32f10x.h"                  // Device header
#include "PWM.h"

void Motor_Init(void)
{
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA,ENABLE);
	
	//c初始化电机的两个角（A4和A5,A6,A7）
	GPIO_InitTypeDef GPIO_InitStructure;
	GPIO_InitStructure.GPIO_Mode=GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin=GPIO_Pin_4|GPIO_Pin_5|GPIO_Pin_6|GPIO_Pin_7;
	GPIO_InitStructure.GPIO_Speed=GPIO_Speed_50MHz;
	GPIO_Init(GPIOA,&GPIO_InitStructure);
	
	PWM_Init();
	
}

void LeftMotor_Speed(int8_t Speed)
{
		if(Speed>0)
		{
			GPIO_SetBits(GPIOA,GPIO_Pin_4);
			GPIO_ResetBits(GPIOA,GPIO_Pin_5);
			PWM_SetCompare2(Speed);
		}
		else if(Speed==0)
		{
			GPIO_SetBits(GPIOA,GPIO_Pin_4);
			GPIO_SetBits(GPIOA,GPIO_Pin_5);
			PWM_SetCompare2(Speed);
		}
		else
		{
			GPIO_ResetBits(GPIOA,GPIO_Pin_4);
			GPIO_SetBits(GPIOA,GPIO_Pin_5);
			PWM_SetCompare2(-Speed);// CCR的值为正，所以Speed前面加负号
		}
}
void RightMotor_Speed(int8_t Speed)
{
		if(Speed>0)
		{
			GPIO_SetBits(GPIOA,GPIO_Pin_6);
			GPIO_ResetBits(GPIOA,GPIO_Pin_7);
			PWM_SetCompare3(Speed);
		}
		else if(Speed==0)
		{
			GPIO_SetBits(GPIOA,GPIO_Pin_6);
			GPIO_SetBits(GPIOA,GPIO_Pin_7);
			PWM_SetCompare3(Speed);
		}
		else
		{
			GPIO_ResetBits(GPIOA,GPIO_Pin_6);
			GPIO_SetBits(GPIOA,GPIO_Pin_7);
			PWM_SetCompare3(-Speed);// CCR的值为正，所以Speed前面加负号
		}
}

