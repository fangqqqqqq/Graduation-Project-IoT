import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import PIL.Image, PIL.ImageTk
import serial
import threading
import time
import queue
import numpy as np
import os
import re  # 【新增】正则表达式库，用于解析传感器数据
import requests  # 【新增】网络请求库，用于控制灯光
from ultralytics import YOLO


# ============================================================================
# 📷 1. 视频流捕获类 (移至顶部以防止引用报错，逻辑未变)
# ============================================================================
class MyVideoCapture:
    def __init__(self, video_source):
        self.video_source = video_source
        self.vid = cv2.VideoCapture(video_source)
        self.q = queue.Queue(maxsize=1)
        self.running = True
        self.thread = threading.Thread(target=self._reader)
        self.thread.daemon = True
        self.thread.start()

    def _reader(self):
        while self.running:
            if self.vid.isOpened():
                ret, frame = self.vid.read()
                if not ret:
                    self.vid.release()
                    time.sleep(1)
                    continue
                if not self.q.empty():
                    try:
                        self.q.get_nowait()
                    except queue.Empty:
                        pass
                self.q.put((ret, frame))
            else:
                time.sleep(0.5)

    def get_frame(self):
        try:
            return self.q.get(timeout=0.1)
        except queue.Empty:
            return (False, None)

    def __del__(self):
        self.running = False
        if self.vid.isOpened(): self.vid.release()


# ============================================================================
# 🎮 2. 主控制器类
# ============================================================================
class SmartCarController:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.geometry("1150x980")

        # === 🧠 0. 加载 YOLO 模型 (逻辑不变) ===
        print("正在加载 YOLOv8 模型，请稍候...")
        try:
            # ⚠️ 保持你的原始路径不变
            self.model = YOLO(r'D:\Pycharm\workplace\Graduation_project\runs\detect\train4\weights\best.pt')
            print("✅ 模型加载成功！(Using train4)")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            self.model = None

        self.ai_enabled = True
        self.rotation_state = 2  # 默认倒置
        self.photo_counter = 0
        self.save_dir = "data_collection"
        if not os.path.exists(self.save_dir): os.makedirs(self.save_dir)

        self.warning_persistence = 0
        self.auto_patrol_mode = False
        self.is_avoiding = False

        # === 🎨 1. 界面配色 ===
        self.style_cfg = {
            "bg_main": "#1e1e2e", "bg_panel": "#282a36",
            "text_main": "#f8f8f2", "text_dim": "#6272a4",
            "accent": "#8be9fd", "btn_stop": "#ff5555",
            "btn_go": "#50fa7b", "btn_normal": "#44475a",
            "btn_func": "#bd93f9", "btn_auto": "#ffb86c",
            "btn_refresh": "#00ced1",
            "btn_track": "#6a5acd",
            "btn_avoid": "#cd5c5c"
        }
        self.window.configure(bg=self.style_cfg["bg_main"])

        # === ⚙️ 2. 核心配置 ===
        # 提取IP地址，方便控制灯光 (从 video_source 字符串中提取)
        self.video_source = "http://192.168.0.123:81/stream"
        self.esp_ip = "192.168.0.123"  # 默认IP

        self.default_com = "COM12"
        self.ser = None
        self.is_connected = False
        self.key_pressed = None

        # === 🖥️ 3. 界面构建 ===
        self.create_ui()

        # === 📷 4. 视频流启动 ===
        self.vid = MyVideoCapture(self.video_source)
        self.delay = 15
        self.update_video()

        # === 🎮 5. 按键绑定 ===
        self.bind_keys()

    def create_ui(self):
        # 标题栏
        header = tk.Frame(self.window, bg=self.style_cfg["bg_main"])
        header.pack(fill=tk.X, pady=(15, 10))
        tk.Label(header, text="STM32 & ESP32 智能巡检终端", font=("Microsoft YaHei", 22, "bold"),
                 bg=self.style_cfg["bg_main"], fg=self.style_cfg["accent"]).pack()
        tk.Label(header, text=f"System Ready | V12.0 (Environment & Light)", font=("Arial", 10),
                 bg=self.style_cfg["bg_main"], fg=self.style_cfg["text_dim"]).pack()

        container = tk.Frame(self.window, bg=self.style_cfg["bg_main"])
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # ====== 左侧：视频监控区 ======
        monitor_frame = tk.LabelFrame(container, text=" 实时视频流 (LIVE FEED) ", font=("Microsoft YaHei", 10, "bold"),
                                      bg=self.style_cfg["bg_main"], fg=self.style_cfg["accent"], bd=2)
        monitor_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)

        canvas_container = tk.Frame(monitor_frame, bg="black")
        canvas_container.pack(expand=True)
        self.canvas = tk.Canvas(canvas_container, width=640, height=480, bg="black", highlightthickness=0)
        self.canvas.pack(pady=10)

        status_bar = tk.Frame(monitor_frame, bg="black")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        self.video_status = tk.Label(status_bar, text="初始化中...", bg="black", fg="gray",
                                     font=("Microsoft YaHei", 10))
        self.video_status.pack(side=tk.LEFT)
        tk.Button(status_bar, text="🔄 刷新画面/重连", command=self.refresh_video_stream,
                  bg=self.style_cfg["btn_refresh"], fg="black", font=("Microsoft YaHei", 9, "bold")).pack(side=tk.RIGHT)

        # ====== 右侧：总控制台 ======
        ctrl_panel = tk.Frame(container, bg=self.style_cfg["bg_main"])
        ctrl_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10)

        # --- 模块1：系统连接 ---
        sys_box = self.create_group_box(ctrl_panel, "1. 系统连接")
        row1 = tk.Frame(sys_box, bg=self.style_cfg["bg_panel"])
        row1.pack(fill=tk.X, pady=5)
        tk.Label(row1, text="端口:", bg=self.style_cfg["bg_panel"], fg="white").pack(side=tk.LEFT)
        self.port_entry = tk.Entry(row1, width=8, bg="#444", fg="white")
        self.port_entry.insert(0, self.default_com)
        self.port_entry.pack(side=tk.LEFT, padx=5)
        self.btn_connect = tk.Button(row1, text="连接蓝牙", command=self.toggle_connection,
                                     bg=self.style_cfg["btn_normal"], fg="white", width=12)
        self.btn_connect.pack(side=tk.LEFT, padx=5)
        self.status_label = tk.Label(sys_box, text="状态: 等待连接", bg=self.style_cfg["bg_panel"], fg="gray")
        self.status_label.pack(fill=tk.X, pady=2)

        # ==============================================================
        # 🟢 新增模块：环境感知 (美化版)
        # ==============================================================
        sensor_box = self.create_group_box(ctrl_panel, "1.5 环境感知 (实时)")

        # 使用 Frame 来布局三个数据
        data_frame = tk.Frame(sensor_box, bg=self.style_cfg["bg_panel"])
        data_frame.pack(fill=tk.X, pady=8)

        # 定义通用样式
        lbl_font = ("Arial", 12, "bold")

        # 1. 距离 (青色)
        self.lbl_dist = tk.Label(data_frame, text="📏 -- cm", font=lbl_font, fg="#00ffff", bg=self.style_cfg["bg_panel"])
        self.lbl_dist.pack(side=tk.LEFT, expand=True)

        # 2. 温度 (橙色)
        self.lbl_temp = tk.Label(data_frame, text="🌡️ -- ℃", font=lbl_font, fg="#ff7f50", bg=self.style_cfg["bg_panel"])
        self.lbl_temp.pack(side=tk.LEFT, expand=True)

        # 3. 湿度 (淡蓝)
        self.lbl_humi = tk.Label(data_frame, text="💧 -- %", font=lbl_font, fg="#87cefa", bg=self.style_cfg["bg_panel"])
        self.lbl_humi.pack(side=tk.LEFT, expand=True)

        # ==============================================================
        # 🟢 新增模块：补光灯控制
        # ==============================================================
        light_box = self.create_group_box(ctrl_panel, "1.6 摄像头补光灯")
        light_row = tk.Frame(light_box, bg=self.style_cfg["bg_panel"])
        light_row.pack(fill=tk.X, pady=5)

        tk.Label(light_row, text="亮度调节:", fg="white", bg=self.style_cfg["bg_panel"],
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=10)

        # 滑块: 0-255，默认 0 (关闭)
        self.light_scale = tk.Scale(light_row, from_=0, to=255, orient=tk.HORIZONTAL, length=200,
                                    bg=self.style_cfg["bg_panel"], fg="white",
                                    troughcolor="#444", activebackground=self.style_cfg["accent"],
                                    highlightthickness=0, borderwidth=0,
                                    command=self.on_light_change)  # 拖动触发
        self.light_scale.set(0)  # 默认关闭
        self.light_scale.pack(side=tk.LEFT, padx=5)

        # --- 模块2：手动驾驶 ---
        drive_box = self.create_group_box(ctrl_panel, "2. 手动驾驶 & AI")
        row2 = tk.Frame(drive_box, bg=self.style_cfg["bg_panel"])
        row2.pack(fill=tk.X, pady=2)
        self.btn_ai = tk.Button(row2, text="AI识别: 开", command=self.toggle_ai,
                                bg=self.style_cfg["btn_go"], fg="black", width=10)
        self.btn_ai.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        rot_texts = ["转: 0°", "转: 90°", "转: 180°", "转: 270°"]
        self.btn_rotate = tk.Button(row2, text=rot_texts[self.rotation_state], command=self.toggle_rotation,
                                    bg=self.style_cfg["btn_func"], fg="black", width=10)
        self.btn_rotate.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.create_drive_buttons(drive_box)

        # --- 模块3：云台与拍摄 ---
        cam_box = self.create_group_box(ctrl_panel, "3. 云台与拍摄")
        g_row = tk.Frame(cam_box, bg=self.style_cfg["bg_panel"])
        g_row.pack(fill=tk.X, pady=5)
        tk.Button(g_row, text="🔼 云台抬升", command=lambda: self.send_cmd(b'R', "云台升"),
                  bg="#555", fg="white").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(g_row, text="🔽 云台下俯", command=lambda: self.send_cmd(b'Q', "云台降"),
                  bg="#555", fg="white").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Button(cam_box, text="📸 截图保存 (P)", command=lambda: self.save_snapshot(None),
                  bg="#FFD700", fg="black", font=("Microsoft YaHei", 10, "bold")).pack(fill=tk.X, pady=5)

        # --- 模块4：自动模式 ---
        mode_box = self.create_group_box(ctrl_panel, "4. 自动驾驶模式")
        tk.Label(mode_box, text="STM32 硬件模式:", bg=self.style_cfg["bg_panel"], fg="gray").pack(anchor=tk.W)
        hw_row = tk.Frame(mode_box, bg=self.style_cfg["bg_panel"])
        hw_row.pack(fill=tk.X, pady=5)
        tk.Button(hw_row, text="🛤️ 循迹模式", command=lambda: self.send_cmd(b'G', "循迹"),
                  bg=self.style_cfg["btn_track"], fg="white", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, fill=tk.X,
                                                                                                expand=True, padx=2)
        tk.Button(hw_row, text="🚧 避障模式", command=lambda: self.send_cmd(b'H', "避障"),
                  bg=self.style_cfg["btn_avoid"], fg="white", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, fill=tk.X,
                                                                                                expand=True, padx=2)

        tk.Label(mode_box, text="Python 视觉模式:", bg=self.style_cfg["bg_panel"], fg="gray").pack(anchor=tk.W,
                                                                                                   pady=(5, 0))
        self.btn_auto = tk.Button(mode_box, text="🤖 开启 AI 自动巡逻", command=self.toggle_auto_patrol,
                                  bg=self.style_cfg["btn_auto"], fg="black", font=("Microsoft YaHei", 10, "bold"))
        self.btn_auto.pack(fill=tk.X, pady=5)

    # === 🟢 新增：灯光控制逻辑 ===
    def on_light_change(self, val):
        # 使用线程发送请求，防止拖动滑块时界面卡顿
        threading.Thread(target=self.send_light_cmd, args=(val,), daemon=True).start()

    def send_light_cmd(self, val):
        try:
            # 构造 URL: http://192.168.0.123/control?var=led_intensity&val=XXX
            # 注意: 这里使用 80 端口 (默认 HTTP)，不是 81 (视频流端口)
            url = f"http://{self.esp_ip}/control?var=led_intensity&val={val}"
            requests.get(url, timeout=0.5)
        except Exception:
            pass  # 忽略网络错误，不弹窗打扰

    # === 🟢 修改：系统连接 (增加数据读取线程) ===
    def toggle_connection(self):
        if not self.is_connected:
            try:
                port = self.port_entry.get()
                self.ser = serial.Serial(port, 9600, timeout=0.1, write_timeout=0.5)
                self.is_connected = True
                self.btn_connect.config(text="断开", bg=self.style_cfg["btn_stop"])
                self.status_label.config(text=f"状态: 已连接 {port}", fg=self.style_cfg["btn_go"])

                # 🔥🔥🔥 连接成功后，启动后台线程监听传感器数据
                threading.Thread(target=self.serial_read_loop, daemon=True).start()

            except Exception as e:
                messagebox.showerror("错误", str(e))
        else:
            if self.ser: self.ser.close()
            self.is_connected = False
            self.btn_connect.config(text="连接蓝牙", bg=self.style_cfg["btn_normal"])
            self.status_label.config(text="状态: 已断开", fg="gray")

    # === 🟢 新增：串口数据读取循环 ===
    def serial_read_loop(self):
        """后台线程：不断读取串口发来的温湿度和距离数据"""
        while self.is_connected and self.ser and self.ser.is_open:
            try:
                # 读取一行数据
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    # 使用正则解析格式: #D:25.5,T:28,H:60*
                    match = re.search(r"#D:([\d\.]+),T:(\d+),H:(\d+)\*", line)
                    if match:
                        dist, temp, humi = match.groups()
                        # 在主线程更新 UI (线程安全)
                        self.window.after(0, lambda: self.update_sensor_ui(dist, temp, humi))
            except Exception:
                pass
            time.sleep(0.05)  # 稍微休眠释放 CPU

    # === 🟢 新增：更新 UI 数值 ===
    def update_sensor_ui(self, d, t, h):
        self.lbl_dist.config(text=f"📏 {d} cm")
        self.lbl_temp.config(text=f"🌡️ {t} ℃")
        self.lbl_humi.config(text=f"💧 {h} %")

    # =========================================================
    # 下面的代码（视频流、YOLO、控制逻辑）保持原样
    # =========================================================

    def refresh_video_stream(self):
        print("尝试重连视频流...")
        self.video_status.config(text="⏳ 正在重连...", fg="yellow")
        if self.vid: self.vid.running = False
        self.window.after(500, self._restart_vid)

    def _restart_vid(self):
        try:
            self.vid = MyVideoCapture(self.video_source)
            print("✅ 视频流重启指令已发送")
        except Exception as e:
            print(f"重连失败: {e}")

    def update_video(self):
        ret, frame = self.vid.get_frame()
        if ret:
            self.video_status.config(text="● 信号正常 (LIVE)", fg=self.style_cfg["btn_go"])

            if self.rotation_state == 1:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation_state == 2:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation_state == 3:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            frame = cv2.filter2D(frame, -1, kernel)

            # AI 检测
            if self.ai_enabled and self.model:
                results = self.model(frame, verbose=False, conf=0.45)
                annotated_frame = results[0].plot()

                detected = False
                for box in results[0].boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    w = x2 - x1
                    h = y2 - y1
                    if w > 30 and h > 30 and w < 600:
                        detected = True
                        break

                if detected: self.warning_persistence = 10

                if self.warning_persistence > 0:
                    cv2.putText(annotated_frame, "POTHOLE DETECTED!", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    self.warning_persistence -= 1

                # 自动巡逻逻辑
                if self.auto_patrol_mode and not self.is_avoiding:
                    if self.warning_persistence > 0:
                        self.is_avoiding = True
                        threading.Thread(target=self.perform_avoidance_maneuver).start()
                    else:
                        self.send_cmd(b'@', "【自动】巡逻前进")

                display_frame = cv2.resize(annotated_frame, (640, 480))
                img_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            else:
                display_frame = cv2.resize(frame, (640, 480))
                img_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)

            self.photo = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(img_rgb))
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        else:
            self.video_status.config(text="❌ 信号中断 (等待刷新...)", fg="red")

        self.window.after(self.delay, self.update_video)

    def perform_avoidance_maneuver(self):
        try:
            self.send_cmd(b'B', "【自动】停车")
            time.sleep(2.0)
            if not self.auto_patrol_mode: return
            self.send_cmd(b'A', "【自动】后退")
            time.sleep(0.8)
            self.send_cmd(b'F', "【自动】转向")
            time.sleep(0.6)
            self.send_cmd(b'B', "【自动】准备恢复")
            time.sleep(0.5)
        except:
            pass
        finally:
            self.is_avoiding = False

    def toggle_auto_patrol(self):
        self.auto_patrol_mode = not self.auto_patrol_mode
        if self.auto_patrol_mode:
            self.btn_auto.config(text="🛑 停止自动巡逻", bg=self.style_cfg["btn_stop"])
            messagebox.showinfo("提示", "视觉自动巡逻已启动！")
        else:
            self.btn_auto.config(text="🤖 开启 AI 自动巡逻", bg=self.style_cfg["btn_auto"])
            self.send_cmd(b'B', "停止自动巡逻")
            self.is_avoiding = False

    def create_drive_buttons(self, parent):
        pad = tk.Frame(parent, bg=self.style_cfg["bg_panel"])
        pad.pack(pady=5)
        btns = [
            ("↖ 左旋(Q)", b'F', 0, 0), ("↑ 前进(W)", b'@', 0, 1), ("↗ 右旋(E)", b'E', 0, 2),
            ("← 左转(A)", b'C', 1, 0), ("🛑 停止", b'B', 1, 1), ("→ 右转(D)", b'D', 1, 2),
            ("↓ 后退(S)", b'A', 2, 1)
        ]
        for txt, cmd, r, c in btns:
            color = self.style_cfg["btn_stop"] if "停止" in txt else (
                self.style_cfg["btn_go"] if "前进" in txt else self.style_cfg["btn_normal"])
            btn = tk.Button(pad, text=txt, bg=color, fg="white", font=("Microsoft YaHei", 9, "bold"), width=8, height=2)
            btn.grid(row=r, column=c, padx=3, pady=3)
            if "停止" in txt:
                btn.configure(command=self.stop_action)
            else:
                btn.bind('<ButtonPress-1>', lambda e, c=cmd, t=txt: self.send_cmd(c, t))
                btn.bind('<ButtonRelease-1>', lambda e: self.stop_action())

    def toggle_ai(self):
        self.ai_enabled = not self.ai_enabled
        self.btn_ai.config(text=f"AI识别: {'开' if self.ai_enabled else '关'}",
                           bg=self.style_cfg["btn_go"] if self.ai_enabled else self.style_cfg["btn_normal"],
                           fg="black" if self.ai_enabled else "white")

    def toggle_rotation(self):
        self.rotation_state = (self.rotation_state + 1) % 4
        rot_texts = ["转: 0°", "转: 90°", "转: 180°", "转: 270°"]
        self.btn_rotate.config(text=rot_texts[self.rotation_state])

    def create_group_box(self, parent, title):
        frame = tk.LabelFrame(parent, text=f" {title} ", font=("Microsoft YaHei", 10, "bold"),
                              bg=self.style_cfg["bg_panel"], fg=self.style_cfg["accent"], bd=1)
        frame.pack(fill=tk.X, padx=10, pady=5, ipady=5)
        return frame

    def bind_keys(self):
        self.window.bind('<KeyPress-w>', lambda e: self.on_key_press(b'@', '前进', 'w'))
        self.window.bind('<KeyPress-s>', lambda e: self.on_key_press(b'A', '后退', 's'))
        self.window.bind('<KeyPress-a>', lambda e: self.on_key_press(b'C', '左转', 'a'))
        self.window.bind('<KeyPress-d>', lambda e: self.on_key_press(b'D', '右转', 'd'))
        self.window.bind('<KeyPress-q>', lambda e: self.on_key_press(b'F', '左旋', 'q'))
        self.window.bind('<KeyPress-e>', lambda e: self.on_key_press(b'E', '右旋', 'e'))
        self.window.bind('<space>', lambda e: self.stop_action())
        self.window.bind('<KeyRelease-w>', self.on_key_release)
        self.window.bind('<KeyRelease-s>', self.on_key_release)
        self.window.bind('<KeyRelease-a>', self.on_key_release)
        self.window.bind('<KeyRelease-d>', self.on_key_release)
        self.window.bind('<KeyRelease-q>', self.on_key_release)
        self.window.bind('<KeyRelease-e>', self.on_key_release)
        self.window.bind('<KeyPress-p>', self.save_snapshot)

    def save_snapshot(self, event):
        ret, frame = self.vid.get_frame()
        if ret:
            if self.rotation_state == 2: frame = cv2.rotate(frame, cv2.ROTATE_180)
            filename = f"{self.save_dir}/train_data_{self.photo_counter}.jpg"
            cv2.imwrite(filename, frame)
            self.video_status.config(text=f"📸 已存入: {filename}", fg="yellow")
            self.photo_counter += 1
        else:
            self.video_status.config(text="⚠️ 无信号，无法截图", fg="red")

    def on_key_press(self, cmd, name, key_char):
        if self.key_pressed == key_char: return
        self.key_pressed = key_char
        self.send_cmd(cmd, name)

    def on_key_release(self, event):
        self.stop_action()

    def stop_action(self):
        self.key_pressed = None
        self.send_cmd(b'B', "停止")

    def send_cmd(self, cmd_byte, action_name):
        if self.is_connected and self.ser:
            try:
                self.ser.write(cmd_byte);
                self.status_label.config(text=f">> {action_name}",
                                         fg=self.style_cfg["accent"])
            except:
                pass
        else:
            print(f"[模拟发送] {cmd_byte.decode(errors='ignore')} ({action_name})")


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartCarController(root, "STM32 & ESP32 智能巡检终端 V12.0")
    root.mainloop()