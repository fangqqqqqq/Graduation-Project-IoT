#include "esp_camera.h"
#include <WiFi.h>

// ===========================
// 引脚定义 (直接定义，防止 board_config.h 缺失或错误)
// 适配 AI-Thinker ESP32-CAM 标准板
// ===========================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM       5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===========================
// 1. 设置 Wi-Fi 账号密码
// ===========================
const char *ssid = "fangq";
const char *password = "010607fgq";

// ===========================
// 2. 设置静态 IP 地址
// ===========================
IPAddress local_IP(10, 181, 200, 123);
IPAddress gateway(10, 181, 200, 223);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(10, 181, 200, 223);

void startCameraServer();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  
  // ========================================================
  // 🔥🔥🔥 核心修改：清晰度与延迟的黄金平衡点 🔥🔥🔥
  // ========================================================
  
  // 1. 修改分辨率为 VGA (640x480)
  // 之前的 QVGA (320x240) 拉伸到电脑屏幕上会很糊。
  // VGA 是 YOLO 和 Python 界面显示的最佳原生分辨率。
  config.frame_size = FRAMESIZE_VGA; 

  config.pixel_format = PIXFORMAT_JPEG; 
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  
  // 2. 提升画质 (数值越小画质越高)
  // 12 是性价比之王。20 会有马赛克，10 以下带宽压力太大。
  config.jpeg_quality = 12;

  // 3. 保持极低延迟策略
  // 仅使用 1 个帧缓存，确保看到永远是最新一帧，不排队。
  config.fb_count = 1;

  // ========================================================

  // 初始化摄像头
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // 传感器调整
  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1); 
    s->set_saturation(s, -2); 
  }
  
  // AI-Thinker 模组通常需要垂直/水平翻转
#if defined(CAMERA_MODEL_AI_THINKER)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

  // ===========================
  // 🔥 LED 补光灯配置 (适配 ESP32 Core 3.0+)
  // ===========================
  // ledcAttach(引脚号, 频率, 分辨率)
  ledcAttach(4, 5000, 8); 
  // ledcWrite(引脚号, 亮度值)
  ledcWrite(4, 0); // 默认关闭

  // Wi-Fi 连接
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS)) {
    Serial.println("STA Failed to configure");
  }

  WiFi.begin(ssid, password);
  // 稍微优化 WiFi 连接策略
  WiFi.setSleep(false); // 关闭 WiFi 省电模式，降低延迟

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  // 启动 Web 服务器
  startCameraServer();

  Serial.print("Camera Ready! Use 'http://");
  Serial.print(WiFi.localIP());
  Serial.println("' to connect");
}

void loop() {
  delay(10000);
}