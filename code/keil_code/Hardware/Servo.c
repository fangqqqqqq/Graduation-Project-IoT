#include "stm32f10x.h"                  // Device header
#include "PWM.h"
#include "Delay.h"
float Servo_Angle=90;
extern uint8_t Servo_Flag;
void Servo_Init(void)
{
	PWM_Init();	
}

// 0      500
// 180    2500

void Servo_SetAngle(float Angle)
{
	PWM_SetCompare4(Angle/180*2000+500);
}

void Servo_SetAngle_Plus(void)
{
	if(Servo_Flag==1)
	{
		Servo_Flag=0;
	Servo_Angle=Servo_Angle+20;
	
	if(Servo_Angle==180)
	{
		Servo_Angle=180;
	}
	PWM_SetCompare4(Servo_Angle/180*2000+500);
	Delay_ms(500);
 }
}
void Servo_SetAngle_Mins(void)
{
	if(Servo_Flag==1)
	{
		Servo_Flag=0;
	Servo_Angle=Servo_Angle-20;
	if(Servo_Angle==0)
	{
		Servo_Angle=0;
	}
	PWM_SetCompare4(Servo_Angle/180*2000+500);
	Delay_ms(500);
	}
}
