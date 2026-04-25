import tkinter as tk
from tkinter import messagebox, filedialog  # 🔥 引入 filedialog
import cv2
import PIL.Image, PIL.ImageTk
import serial
import threading
import time
import numpy as np
import os
import re
import requests
from ultralytics import YOLO

# 引入模块
import ui_module
from video_module import MyVideoCapture
from database_module import DatabaseManager


class SmartCarController:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.geometry("1150x800")

        # === 💾 数据库 ===
        print("正在连接数据库...")
        self.db = DatabaseManager("patrol_record.db")

        # === 🧠 AI模型 ===
        print("正在加载 YOLOv8 模型...")
        try:
            self.model = YOLO(
                r'D:\Pycharm\workplace\Graduation_project\runs\detect\city_patrol_cpu_run\weights\best.pt')
            print("✅ 模型加载成功！")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            self.model = None

        self.ai_enabled = True
        self.rotation_state = 0
        self.photo_counter = 0

        # 🔥 修改点：增加用于存放手动上传分析图片的文件夹
        self.manual_dir = "data_manual"  # 手动抓拍
        self.auto_dir = "data_evidence"  # 自动留证
        self.pattern_dir = "data_patterns"  # 通用识别结果

        if not os.path.exists(self.manual_dir): os.makedirs(self.manual_dir)
        if not os.path.exists(self.auto_dir): os.makedirs(self.auto_dir)
        if not os.path.exists(self.pattern_dir): os.makedirs(self.pattern_dir)

        # 模式识别专用变量
        self.selected_image_path = ""

        self.warning_persistence = 0
        self.auto_patrol_mode = False
        self.is_avoiding = False
        self.last_patrol_cmd_time = 0
        self.save_cooldowns = {}
        # 🔥 新增：环境快照与宏观任务管理
        self.current_session_id = None  # None 表示没有在执行自动巡逻任务
        self.current_temp = 0  # 实时缓存的温度
        self.current_humi = 0  # 实时缓存的湿度

        # === 🎨 界面配色 ===
        self.style_cfg = {
            "bg_main": "#1e1e2e", "bg_panel": "#282a36",
            "text_main": "#f8f8f2", "text_dim": "#6272a4",
            "accent": "#8be9fd", "btn_stop": "#ff5555",
            "btn_go": "#50fa7b", "btn_normal": "#44475a",
            "btn_func": "#bd93f9", "btn_auto": "#ffb86c",
            "btn_refresh": "#00ced1",
            "btn_track": "#6a5acd", "btn_avoid": "#cd5c5c"
        }
        self.window.configure(bg=self.style_cfg["bg_main"])

        # === ⚙️ 硬件连接 ===
        self.video_source = "http://10.181.200.123:81/stream"
        self.esp_ip = "10.181.200.123"
        self.default_com = "COM12"
        self.ser = None
        self.is_connected = False
        self.key_pressed = None

        # === 🖥️ 构建界面 ===
        ui_module.setup_ui(self)

        # === 📷 视频 ===
        self.vid = MyVideoCapture(self.video_source)
        self.delay = 15
        self.update_video()

        # === 🎮 键盘 ===
        self.bind_keys()

    # === 视频循环 ===
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

            if self.ai_enabled and self.model:
                results = self.model(frame, verbose=False, conf=0.15)
                annotated_frame = frame.copy()

                class_thresholds = {'can': 0.60, 'pothole': 0.20, 'manhole': 0.85}
                colors = {'can': (255, 0, 255), 'manhole': (0, 0, 255), 'pothole': (0, 255, 0)}

                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    cls_name = results[0].names[cls_id]
                    target_conf = class_thresholds.get(cls_name, 0.6)

                    if conf > target_conf:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        if (x2 - x1) > 600: continue

                        color = colors.get(cls_name, (0, 255, 255))
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated_frame, f"{cls_name} {conf:.2f}", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                        if cls_name == 'pothole': self.warning_persistence = 10

                        current_time = time.time()
                        last_save = self.save_cooldowns.get(cls_name, 0)
                        if conf > target_conf + 0.05 and (current_time - last_save > 10.0):
                            try:
                                timestamp = time.strftime("%Y%m%d_%H%M%S")
                                img_name = f"{timestamp}_{cls_name}.jpg"
                                save_path = os.path.join(self.auto_dir, img_name)
                                if not os.path.exists(save_path):
                                    cv2.imwrite(save_path, frame)
                                    # 🔥 传入当前的任务批次、类别、置信度、路径，以及当时的温湿度！
                                    threading.Thread(target=self.db.insert_detection_event,
                                                     args=(self.current_session_id, cls_name, conf, save_path,
                                                           self.current_temp, self.current_humi), daemon=True).start()
                                    self.save_cooldowns[cls_name] = current_time
                                    print(f"📸 记录证据: {cls_name}")
                            except Exception:
                                pass

                if self.warning_persistence > 0:
                    cv2.putText(annotated_frame, "POTHOLE DETECTED!", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (0, 0, 255), 2)
                    self.warning_persistence -= 1

                if self.auto_patrol_mode and not self.is_avoiding:
                    if self.warning_persistence > 0:
                        self.is_avoiding = True
                        threading.Thread(target=self.perform_avoidance_maneuver).start()
                    else:
                        if time.time() - self.last_patrol_cmd_time > 0.5:
                            self.send_cmd(b'@', "【自动】巡逻")
                            self.last_patrol_cmd_time = time.time()

                display_frame = cv2.resize(annotated_frame, (640, 480))
                img_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            else:
                display_frame = cv2.resize(frame, (640, 480))
                img_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)

            self.photo = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(img_rgb))
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        else:
            self.video_status.config(text="❌ 信号中断", fg="red")

        self.window.after(self.delay, self.update_video)

    # === 传感器数据循环 ===
    def serial_read_loop(self):
        last_save_time = 0
        last_saved_temp = -999
        last_saved_humi = -999

        while self.is_connected and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    match = re.search(r"#D:([\d\.]+),T:(\d+),H:(\d+)\*", line)
                    if match:
                        dist, temp, humi = match.groups()
                        # 🔥 实时缓存，供摄像头快照使用
                        self.current_temp = int(temp)
                        self.current_humi = int(humi)
                        self.window.after(0, lambda: self.update_sensor_ui(dist, temp, humi))

                        curr = time.time()
                        save = False
                        note = ""
                        if abs(int(temp) - last_saved_temp) >= 1:
                            save, note = True, "温度突变"
                        elif abs(int(humi) - last_saved_humi) >= 2:
                            save, note = True, "湿度突变"
                        elif curr - last_save_time > 60:
                            save, note = True, "定时记录"

                        if save:
                            # 🔥 传入 session_id
                            threading.Thread(target=self.db.insert_sensor_data,
                                             args=(self.current_session_id, float(dist), int(temp), int(humi), note),
                                             daemon=True).start()
                            last_saved_temp, last_saved_humi, last_save_time = int(temp), int(humi), curr
            except Exception:
                pass
            time.sleep(0.05)

    # === 🔥 通用模式识别功能 (新增) ===
    def select_image(self):
        """弹出文件选择器，选择本地图片"""
        file_path = filedialog.askopenfilename(
            title="选择需要分析的照片",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp")]
        )
        if file_path:
            self.selected_image_path = file_path
            display_name = os.path.basename(file_path)
            # 缩短显示路径以免撑破UI
            if len(display_name) > 20: display_name = display_name[:17] + "..."
            self.lbl_pattern_path.config(text=f"📂 已选: {display_name}", fg="white")
            self.lbl_pattern_result.config(text="分析结果: 就绪，请点击分析")

    def analyze_image(self):
        """对选中的图片调用 YOLOv8 进行离线识别"""
        if not self.selected_image_path:
            messagebox.showwarning("提示", "请先点击【上传照片】选择文件！")
            return
        if not self.model:
            messagebox.showerror("错误", "YOLO 模型未成功加载！")
            return

        self.lbl_pattern_result.config(text="分析结果: 正在进行 AI 推理...")
        self.window.update()  # 强制更新 UI 状态

        try:
            # 1. 读取图像
            img = cv2.imread(self.selected_image_path)
            if img is None: raise ValueError("无法读取该图像文件，可能已损坏。")

            # 2. 推理
            results = self.model(img, verbose=False)
            detected_items = []
            annotated_img = img.copy()

            # 3. 绘制检测框与汇总结果
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                cls_name = results[0].names[cls_id]
                detected_items.append(f"{cls_name}({conf:.2f})")

                # 画框
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated_img, f"{cls_name} {conf:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # 4. 更新UI与保存结果
            if detected_items:
                res_str = " | ".join(detected_items)
                self.lbl_pattern_result.config(text=f"发现目标: {res_str}")

                # 保存分析图
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(self.pattern_dir, f"analyzed_{timestamp}.jpg")
                cv2.imwrite(save_path, annotated_img)

                # 弹窗展示识别结果
                cv2.imshow("Analysis Result (Press any key to close)", cv2.resize(annotated_img, (640, 480)))
                cv2.waitKey(0)  # 暂停等待用户按键关闭弹窗
                cv2.destroyAllWindows()
            else:
                self.lbl_pattern_result.config(text="分析结果: 未检测到任何预设目标")
                messagebox.showinfo("分析完毕", "该照片中未检测到目标物。")

        except Exception as e:
            self.lbl_pattern_result.config(text="分析结果: 发生异常")
            messagebox.showerror("识别错误", f"分析过程中出现错误: {str(e)}")

    # === 其它功能函数 ===
    def refresh_video_stream(self):
        self.video_status.config(text="⏳ 重连中...", fg="yellow")
        if self.vid: self.vid.release()
        self.window.after(500, self._restart_vid)

    def _restart_vid(self):
        try:
            self.vid = MyVideoCapture(self.video_source)
        except Exception as e:
            print(e)

    def open_history_window(self):
        from ui_module import HistoryWindow
        HistoryWindow(self.window, self.db)

    def perform_avoidance_maneuver(self):
        try:
            self.send_cmd(b'B', "避障停")
            time.sleep(2.0)
            if not self.auto_patrol_mode: return
            self.send_cmd(b'A', "避障退")
            time.sleep(0.8)
            self.send_cmd(b'F', "避障转")
            time.sleep(0.6)
            self.send_cmd(b'B', "避障毕")
            time.sleep(0.5)
        except:
            pass
        finally:
            self.is_avoiding = False

    def toggle_auto_patrol(self):
        self.auto_patrol_mode = not self.auto_patrol_mode
        if self.auto_patrol_mode:
            # 🔥 开始宏观任务，生成 session_id
            self.current_session_id = self.db.start_session()
            print(f"🚀 新巡逻任务开始，批次号: {self.current_session_id}")

            self.btn_auto.config(text="🛑 停止自动巡逻", bg=self.style_cfg["btn_stop"])
            self.send_cmd(b'@', "开始巡逻")
        else:
            # 🔥 结束宏观任务
            self.db.end_session(self.current_session_id)
            self.current_session_id = None

            self.btn_auto.config(text="🚀 开启自动巡逻", bg=self.style_cfg["btn_auto"])
            self.send_cmd(b'B', "停止巡逻")
            self.is_avoiding = False

    def toggle_ai(self):
        self.ai_enabled = not self.ai_enabled
        self.btn_ai.config(text=f"👁️ 目标识别: {'开' if self.ai_enabled else '关'}",
                           bg=self.style_cfg["btn_go"] if self.ai_enabled else self.style_cfg["btn_normal"])

    def toggle_rotation(self):
        self.rotation_state = (self.rotation_state + 1) % 4
        self.btn_rotate.config(text=f"🔄 画面旋转: {self.rotation_state * 90}°")

    def on_light_change(self, val):
        threading.Thread(target=self.send_light_cmd, args=(val,), daemon=True).start()

    def send_light_cmd(self, val):
        try:
            requests.get(f"http://{self.esp_ip}/control?var=led_intensity&val={val}", timeout=0.5)
        except:
            pass

    def toggle_connection(self):
        if not self.is_connected:
            try:
                self.ser = serial.Serial(self.port_entry.get(), 9600, timeout=0.1)
                self.is_connected = True
                self.btn_connect.config(text="断开", bg=self.style_cfg["btn_stop"])
                self.status_label.config(text=f"状态: ✅ 已连接", fg=self.style_cfg["btn_go"])
                threading.Thread(target=self.serial_read_loop, daemon=True).start()
            except Exception as e:
                messagebox.showerror("错误", str(e))
        else:
            if self.ser: self.ser.close()
            self.is_connected = False
            self.btn_connect.config(text="连接", bg=self.style_cfg["btn_normal"])
            self.status_label.config(text="状态: ❌ 已断开", fg="gray")

    def update_sensor_ui(self, d, t, h):
        self.lbl_dist.config(text=f"📏 {d} cm")
        self.lbl_temp.config(text=f"🌡️ {t} ℃")
        self.lbl_humi.config(text=f"💧 {h} %")

    # === 🔥 键盘绑定 ===
    def bind_keys(self):
        self.window.bind('<KeyPress-w>', lambda e: self.on_key_press(b'@', '前进', 'w'))
        self.window.bind('<KeyPress-s>', lambda e: self.on_key_press(b'A', '后退', 's'))
        self.window.bind('<KeyPress-a>', lambda e: self.on_key_press(b'C', '左转', 'a'))
        self.window.bind('<KeyPress-d>', lambda e: self.on_key_press(b'D', '右转', 'd'))
        self.window.bind('<KeyPress-q>', lambda e: self.on_key_press(b'F', '左旋', 'q'))
        self.window.bind('<KeyPress-e>', lambda e: self.on_key_press(b'E', '右旋', 'e'))

        self.window.bind('<KeyPress-i>', lambda e: self.on_key_press(b'R', '云台升', 'i'))
        self.window.bind('<KeyPress-k>', lambda e: self.on_key_press(b'Q', '云台降', 'k'))

        self.window.bind('<KeyPress-g>', lambda e: self.on_key_press(b'G', '循迹模式', 'g'))
        self.window.bind('<KeyPress-h>', lambda e: self.on_key_press(b'H', '避障模式', 'h'))

        for key in ['w', 's', 'a', 'd', 'q', 'e', 'i', 'k']:
            self.window.bind(f'<KeyRelease-{key}>', self.on_key_release)

        self.window.bind('<space>', lambda e: self.stop_action())
        self.window.bind('<KeyPress-p>', self.save_snapshot)

    def save_snapshot(self, event):
        ret, frame = self.vid.get_frame()
        if ret:
            filename = f"{self.manual_dir}/manual_{self.photo_counter}.jpg"
            cv2.imwrite(filename, frame)
            self.video_status.config(text=f"📸 截图: {filename}", fg="yellow")
            self.photo_counter += 1

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
                self.ser.write(cmd_byte)
                self.status_label.config(text=f">> {action_name}", fg=self.style_cfg["accent"])
            except:
                pass
        else:
            print(f"[发送] {cmd_byte} ({action_name})")


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartCarController(root, "STM32 & ESP32 智能巡检终端 V12.0")
    root.mainloop()