#ifndef __SERIAL_H
#define __SERIAL_H
#include "stdint.h"
#include <stdio.h>
void Serial_Init(void);
void Serial_SendByte(uint8_t Byte);
void Serial_SendArry(uint8_t *Arry,uint16_t Length);
void Serial_SendString(char *String);
uint32_t Serial_Pow(uint32_t x,uint32_t y);
void Serial_SendNumber(uint32_t Number,uint8_t Length);
uint8_t Serial_GetRxFlag(void);
uint8_t Serial_GetRxData(void);
#endif

