#include "stm32f10x.h"                  
#include "Delay.h"
#include "OLED.h"
#include "Motor.h"
#include "SmartCar.h"
#include "Serial.h"
#include "HCSR04.h"
#include "Servo.h"
#include "LineWalking.h"
#include "Buzzer.h"
#include "DHT11.h"
#include <stdio.h>  // 用于 sprintf

uint8_t RxData, Num;
uint8_t Servo_Flag;
float Current_Dist;     
uint8_t Obstacle_Count = 0; 
uint16_t Ignore_Timer = 0; 

// --- 全局变量 ---
uint8_t Temp_Val = 0;       
uint8_t Humi_Val = 0;       
uint16_t Report_Timer = 0;  
uint16_t Display_Timer = 0; 
uint8_t Display_Mode = 0;   // 0:行驶模式, 1:环境模式
char Tx_Buffer[64];         

int main(void)
{
    HCSR04_Init();
    OLED_Init();    
    SmartCar_Init();
    Serial_Init();
    Servo_Init();
    LineWalking_Init();
    Buzzer_Init();
    DHT11_Init();
    
    Servo_SetAngle(90); 
    
    // 开机动画
    OLED_ShowString(1, 1, "System Init...");
    Delay_ms(500);
    OLED_Clear();
    
    // 预先显示静态文字，防止循环刷屏闪烁
    OLED_ShowString(1, 1, "Dist:");
    OLED_ShowString(2, 6, "CM"); 
    OLED_ShowString(3, 1, "Status:");
    
    while(1)
    {
        // ==========================================
        // 1. 传感器数据采集
        // ==========================================
        Current_Dist = HCSR04_Distance();
        
        // 【冲突修复】：千万不要在这里直接 ShowNum，否则会覆盖环境界面的标题！
        
        // 降低 DHT11 读取频率
        static uint16_t DHT_Timer = 0;
        DHT_Timer++;
        if(DHT_Timer > 50) 
        {
            DHT11_Read_Data(&Temp_Val, &Humi_Val);
            DHT_Timer = 0;
        }

        // ==========================================
        // 2. 数据上报 (发送给 Python)
        // ==========================================
        Report_Timer++;
        if(Report_Timer > 20) 
        {
            sprintf(Tx_Buffer, "#D:%.1f,T:%d,H:%d*\r\n", Current_Dist, Temp_Val, Humi_Val);
            Serial_SendString(Tx_Buffer); 
            Report_Timer = 0;
        }

        // ==========================================
        // 3. 核心 OLED 显示逻辑 (统一管理，避免冲突)
        // ==========================================
        
        // 智能切换逻辑：车在动 -> 强制看路况；车不动 -> 轮播看环境
        if(Num != 0 && Num != 3) 
        {
            Display_Mode = 0; // 强制显示行驶数据
        }
        else
        {
            Display_Timer++;
            if(Display_Timer > 300) // 约3秒切换
            {
                Display_Mode = !Display_Mode;
                OLED_Clear(); // 切换瞬间清屏，保证干净
                Display_Timer = 0;
            }
        }

        // --- 分支 A：显示行驶数据 ---
        if(Display_Mode == 0) 
        {
            // 【修复】距离显示移到这里
            OLED_ShowString(1, 1, "Dist:");
            OLED_ShowNum(1, 6, (uint32_t)Current_Dist, 3);
            OLED_ShowString(1, 10, "cm");
            
            OLED_ShowString(3, 1, "Status:");
            
            // 状态显示
            if (Num == 1 && Obstacle_Count >= 2) 
                OLED_ShowString(4, 1, "Auto Avoid!!"); // 最高优先级：正在避障
            else if(Num==1) OLED_ShowString(4,1,"Forward     ");
            else if(Num==3) OLED_ShowString(4,1,"Stop        ");
            else if(Num==9) OLED_ShowString(4,1,"ObstacleMode");
            else if(Num==0) OLED_ShowString(4,1,"Ready       ");
            else OLED_ShowString(4,1,"Running     ");
        }
        // --- 分支 B：显示环境数据 ---
        else 
        {
            OLED_ShowString(1, 1, "Env Monitor  "); // 这样就不会被距离覆盖了
            
            OLED_ShowString(2, 1, "Temp:");
            OLED_ShowNum(2, 6, Temp_Val, 2);
            OLED_ShowString(2, 9, "C");
            
            OLED_ShowString(3, 1, "Humi:");
            OLED_ShowNum(3, 6, Humi_Val, 2);
            OLED_ShowString(3, 9, "%");
            
            OLED_ShowString(4, 1, "             "); // 底部留白
        }
        
        // ==========================================
        // 4. 滤波逻辑
        // ==========================================
        if (Ignore_Timer > 0)
        {
            Ignore_Timer--; 
            Obstacle_Count = 0; 
        }
        else
        {
            if (Current_Dist < 25.0 && Current_Dist > 2.0) Obstacle_Count++;
            else Obstacle_Count = 0;
        }

        // ==========================================
        // 5. 接收指令
        // ==========================================
        if(Serial_GetRxFlag() == 1)
        {
            RxData = Serial_GetRxData();
            Servo_Flag = 1;

            if(RxData == 0x40)      Num = 1; 
            else if(RxData == 0x41) Num = 2; 
            else if(RxData == 0x42) { Num = 3; Car_Stop(); } // 手动停止
            else if(RxData == 0x43) Num = 4; 
            else if(RxData == 0x44) Num = 5; 
            else if(RxData == 0x45) Num = 6; 
            else if(RxData == 0x46) Num = 7; 
            else if(RxData == 0x47) Num = 8; 
            else if(RxData == 0x48) Num = 9; 
            else if(RxData == 0x49) Num = 10;
            else if(RxData == 0x51) Num = 12;
            else if(RxData == 0x52) Num = 13;
            
            // 【优化】删除了这里零散的 OLED_ShowString，统一由上方第3步管理
        }

        // ==========================================
        // 6. 核心控制逻辑 (执行动作)
        // ==========================================
        if (Num == 1 && Obstacle_Count >= 2)
        {
            // 自动避障触发
            AvoidObstacle(); 
            Ignore_Timer = 100; 
            Obstacle_Count = 0; 
        }
        else
        {
            switch(Num)
            {
                case 1: Move_Forward(); break; 
                case 2: Move_Backward(); break;
                case 3: Car_Stop(); break;
                case 4: Turn_Left(40); break;
                case 5: Turn_Right(40); break;
                case 6: Clockwise_Rotation(); break;
                case 7: CounterClockwise_Rotation(); break;
                case 8: LineWalking(); break;
                case 9: 
                    if (Current_Dist < 25.0 && Current_Dist > 2.0) {
                        AvoidObstacle(); 
                        Ignore_Timer = 50;
                    } else {
                        Move_Forward();  
                    }
                    break; 
                case 10: Following(); break;
                case 12: Servo_SetAngle_Plus(); break;
                case 13: Servo_SetAngle_Mins(); break;
                default: break;
            }
        }
    }
}