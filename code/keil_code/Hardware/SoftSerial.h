#ifndef __SOFTSERIAL_H
#define __SOFTSERIAL_H

#include "stm32f10x.h"

// 声明外部变量，相当于告诉整个工程：这个装 GPS 数据的大水缸在这里！
extern char GPS_Buffer[512];
extern uint16_t GPS_Index;

// 初始化函数声明
void SoftSerial_Init(void);

#endif

