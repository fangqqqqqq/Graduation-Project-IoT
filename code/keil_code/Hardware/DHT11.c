#include "stm32f10x.h"                  // Device header
#include "Delay.h"
#include "OLED.h"
uint8_t temperature,humidity;
uint8_t count;
void DHT11_IO_OUT(void)
{
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
	
	GPIO_InitTypeDef GPIO_InitStructure;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOB, &GPIO_InitStructure);				
}

void DHT11_IO_IN(void)
{
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
	
	GPIO_InitTypeDef GPIO_InitStructure;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOB, &GPIO_InitStructure);
			 
}

//复位DHT11
void DHT11_Rst(void)	   
{                 
	DHT11_IO_OUT(); 	//选择输出模式
    GPIO_ResetBits(GPIOB, GPIO_Pin_0); 	//拉低B0
    Delay_ms(20);    	//拉低至少18ms
    GPIO_SetBits(GPIOB, GPIO_Pin_0); 	//拉高B0
    Delay_us(20);    	//主机拉高20~40us
}
//等待DHT11的回应
//返回1:未检测到DHT11的存在
//返回0:存在
uint8_t DHT11_Check(void) 	   
{   
	uint8_t retry=0;
	
	DHT11_IO_IN();//SET INPUT	 
	 
    while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_0)==0 && retry<100)//DHT11会拉低40~80us
	{
		retry++;
		Delay_us(1);
	};	 
	if(retry>=100)return 1;
	else retry=0;
    while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_0)==1 && retry<100)//DHT11拉低后会再次拉高40~80us
	{
		retry++;
		Delay_us(1);
	};
	if(retry>=100)return 1;	    
	return 0;
}
//从DHT11读取一个位
//返回值：1/0
uint8_t DHT11_Read_Bit(void) 			 
{
 	uint8_t retry=0;
	while(GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_0)==1 && retry<100)//等待变为低电平
	{
		retry++;
		Delay_us(1);
	}
	retry=0;
	while(GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_0)==0 && retry<100)//等待变高电平
	{
		retry++;
		Delay_us(1);
	}
	Delay_us(40);//等待40us
	if(GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_0)==1)return 1;
	else return 0;		   
}
//从DHT11读取一个字节
//返回值：读到的数据
uint8_t DHT11_Read_Byte(void)    
{        
	uint8_t i,dat;
	dat=0;
	for (i=0;i<8;i++) 
	{
		dat<<=1; 
		dat|=DHT11_Read_Bit();
  }						    
  return dat;
}
//从DHT11读取一次数据
//temp:温度值(范围:0~50°)
//humi:湿度值(范围:20%~90%)
//返回值：0,正常;1,读取失败
uint8_t DHT11_Read_Data(uint8_t *temp,uint8_t *humi)    
{        
 	uint8_t buf[5];
	uint8_t i;
	DHT11_Rst();
	if(DHT11_Check()==0)
	{
		for(i=0;i<5;i++)//读取40位数据
		{
			buf[i]=DHT11_Read_Byte();
		}
		if((buf[0]+buf[1]+buf[2]+buf[3])==buf[4])
		{
			*humi=buf[0];
			*temp=buf[2];
		}
	}else return 1;
	return 0;	    
}
//初始化DHT11的IO口 DQ 同时检测DHT11的存在
//返回1:不存在
//返回0:存在    	 
uint8_t DHT11_Init(void)
{	 	    
	DHT11_Rst();  //复位DHT11
	return DHT11_Check();//等待DHT11的回应
} 
void DHT11_Value(void)
{
	OLED_Init();
	DHT11_Init();
	OLED_ShowString(1,1,"temperature:");
	OLED_ShowString(2,3,"C");
	OLED_ShowString(3,1,"humidity:");
	OLED_ShowString(4,3,"%");
	while(1)
	{
		DHT11_Read_Data(&temperature, &humidity);
		OLED_ShowNum(2,1,temperature,2);
		OLED_ShowNum(4,1,humidity,2);
		Delay_ms(100);
		count++;
		if(count==15)
		{
			count=0;
			break;
		}
	}
}


