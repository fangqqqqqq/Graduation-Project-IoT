#include "stm32f10x.h"                  // Device header
#include "Motor.h"

void SmartCar_Init(void)
{
	Motor_Init();
}
void Move_Forward(void)
{
	LeftMotor_Speed(30);
	RightMotor_Speed(30);
}
void Move_Backward(void)
{
	LeftMotor_Speed(-40);
	RightMotor_Speed(-40);
}
void Car_Stop(void)
{
	LeftMotor_Speed(0);
	RightMotor_Speed(0);
}
void Turn_Left(int8_t Speed)
{
	LeftMotor_Speed(0);
	RightMotor_Speed(Speed);
}
void Turn_Right(int8_t Speed)
{
	LeftMotor_Speed(Speed);
	RightMotor_Speed(0);
}
void Clockwise_Rotation(void)
{
	LeftMotor_Speed(45);
	RightMotor_Speed(-45);
}
void CounterClockwise_Rotation(void)
{
	LeftMotor_Speed(-45);
	RightMotor_Speed(45);
}
