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
        self.db = DatabaseManager()

        # ==========================================
        # 🔥 新增：方法一 (启动时自动执行断网容灾重传)
        # ==========================================
        print("启动后台容灾同步守护线程...")
        threading.Thread(target=self.db.sync_offline_data, daemon=True).start()

        # === 🧠 AI模型 (主线实时模型) ===
        print("正在加载 YOLOv8 主线模型...")
        try:
            self.model = YOLO(
                r'D:\Pycharm\workplace\Graduation_project\runs\detect\city_patrol_cpu_run\weights\best.pt')
            print("✅ 模型加载成功！")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            self.model = None

        self.ai_enabled = True
        # 🔥 将各个类的默认置信度存在字典中，供两个界面联动使用
        self.class_thresholds = {'can': 0.65, 'pothole': 0.50, 'manhole': 0.65}
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
        self.detection_buffer = {}  # 记录连续识别到的帧数，过滤偶尔一闪而过的误报
        self.push_cooldowns = {}  # 单独控制微信推送的冷却时间（例如60秒推一次）

        # 🔥 新增：环境快照与宏观任务管理
        self.current_session_id = None  # None 表示没有在执行自动巡逻任务
        self.current_temp = 0  # 实时缓存的温度
        self.current_humi = 0  # 实时缓存的湿度

        # 🔥 新增：GPS 逆地理编码缓存
        self.amap_key = "1e320c1d74a40dac82a55d080eeba6e9"
        self.last_location_name = ""
        self.last_resolved_lat = 0.0
        self.last_resolved_lon = 0.0

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
        self.video_source = "http://10.172.191.123:81/stream"
        self.esp_ip = "10.172.191.123"
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

                colors = {'can': (255, 0, 255), 'manhole': (0, 0, 255), 'pothole': (0, 255, 0)}

                current_detected_classes = set()
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    cls_name = results[0].names[cls_id]
                    # 使用全局动态阈值，不再是硬编码
                    target_conf = self.class_thresholds.get(cls_name, 0.6)

                    if conf > target_conf:
                        current_detected_classes.add(cls_name)  # 记录本帧抓到了它
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        if (x2 - x1) > 600: continue

                        color = colors.get(cls_name, (0, 255, 255))
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated_frame, f"{cls_name} {conf:.2f}", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                        if cls_name == 'pothole': self.warning_persistence = 10

                        # ==========================================
                        # 🔥 核心改进：防抖与双重冷却机制
                        # ==========================================
                        # 1. 累加连续识别帧数
                        self.detection_buffer[cls_name] = self.detection_buffer.get(cls_name, 0) + 1

                        # 2. 只有连续 5 帧都稳定识别到，才认为是真正的目标（避免反光误报）
                        if self.detection_buffer[cls_name] >= 5:
                            current_time = time.time()
                            last_save = self.save_cooldowns.get(cls_name, 0)
                            last_push = self.push_cooldowns.get(cls_name, 0)

                            # 【本地留证冷却】(10.0秒拍一次照存数据库)
                            if conf > target_conf + 0.05 and (current_time - last_save > 10.0):
                                try:
                                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                                    img_name = f"{timestamp}_{cls_name}.jpg"
                                    save_path = os.path.join(self.auto_dir, img_name)
                                    if not os.path.exists(save_path):
                                        cv2.imwrite(save_path, frame)
                                        # 传入数据库
                                        threading.Thread(target=self.db.insert_detection_event,
                                                         args=(self.current_session_id, cls_name, conf, save_path,
                                                               self.current_temp, self.current_humi),
                                                         daemon=True).start()
                                        self.save_cooldowns[cls_name] = current_time
                                        print(f"📸 记录证据: {cls_name}")

                                        # 【微信推送冷却】(单独限制：60秒才发一条微信消息，防轰炸)
                                        if current_time - last_push > 60.0:
                                            threading.Thread(target=self.send_wechat_alert,
                                                             args=(
                                                                 cls_name, conf, self.current_temp, self.current_humi),
                                                             daemon=True).start()
                                            self.push_cooldowns[cls_name] = current_time

                                except Exception as e:
                                    print(f"保存或推送失败: {e}")

                # 🔥 帧后处理：如果某目标在本帧消失了，清空它的连续识别帧数
                for cls in list(self.detection_buffer.keys()):
                    if cls not in current_detected_classes:
                        self.detection_buffer[cls] = 0

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
                    # 匹配带经纬度的新格式报文
                    match = re.search(r"#D:([\d\.]+),T:(\d+),H:(\d+),La:([\d\.]+),Lo:([\d\.]+)\*", line)
                    if match:
                        dist, temp, humi, raw_lat, raw_lon = match.groups()

                        # 🔥 调用转换函数，把原始数据洗成标准十进制
                        lat = self.convert_nmea_to_decimal(raw_lat)
                        lon = self.convert_nmea_to_decimal(raw_lon)

                        # 实时缓存，供摄像头快照使用
                        self.current_temp = int(temp)
                        self.current_humi = int(humi)

                        # 逆地理编码（带缓存）
                        location_name = self.resolve_location_name(lat, lon)

                        # 刷新UI界面
                        self.window.after(0, lambda ln=location_name: self.update_sensor_ui(dist, temp, humi, lat, lon, ln))

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
                            # 存入数据库 (含 lat, lon 及逆地理编码地名)
                            threading.Thread(target=self.db.insert_sensor_data,
                                             args=(self.current_session_id, float(dist), int(temp), int(humi), lat, lon,
                                                   location_name, note),
                                             daemon=True).start()
                            last_saved_temp, last_saved_humi, last_save_time = int(temp), int(humi), curr
            except Exception:
                pass
            time.sleep(0.05)

    # === 🔥 独立工作台: 图像离线分析核心 ===
    def open_image_analysis_window(self):
        """打开独立的图像分析工作台"""
        from ui_module import ImageAnalysisWindow
        ImageAnalysisWindow(self.window, self)

    def perform_offline_analysis(self, image_path, selected_model, custom_thresholds):
        """供独立工作台调用的核心分析引擎 (支持动态模型切换)"""
        # 防止选择空模型
        if selected_model == "未找到模型文件" or not selected_model.endswith(".pt"):
            return cv2.imread(image_path), "⚠️ 未选择有效的 .pt 模型"

        try:
            # === 1. 智能热加载模型机制 ===
            # 如果是第一次离线分析，或者用户在下拉菜单里换了新模型，才重新加载
            if not hasattr(self, 'offline_model_name') or self.offline_model_name != selected_model or not hasattr(self,
                                                                                                                   'offline_model'):
                print(f"正在加载离线模型: {selected_model} ...")
                from ultralytics import YOLO
                self.offline_model = YOLO(selected_model)  # 加载新模型
                self.offline_model_name = selected_model  # 记录当前加载的模型名
                print("模型加载完成！")

            img = cv2.imread(image_path)
            if img is None: return None, "图像读取失败"

            # === 2. 使用动态加载的离线模型进行推理 ===
            results = self.offline_model(img, verbose=False)
            detected_items = []
            annotated_img = img.copy()

            # === 3. 画框，应用右侧面板传过来的动态阈值 ===
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                cls_name = results[0].names[cls_id]

                # 读取传进来的阈值，如果没设则默认 0.5
                target_conf = custom_thresholds.get(cls_name, 0.5)

                # 只有高于新阈值才画框
                if conf > target_conf:
                    detected_items.append(f"{cls_name}({conf:.2f})")
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated_img, f"{cls_name} {conf:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 255, 0), 2)

            # === 4. 返回处理结果给 UI ===
            if detected_items:
                res_str = " | ".join(detected_items)
                # 可选：保存带框的分析结果到 data_patterns 文件夹
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                cv2.imwrite(os.path.join(self.pattern_dir, f"analyzed_{timestamp}.jpg"), annotated_img)
                return annotated_img, f"发现 {res_str}"
            else:
                return annotated_img, "未检测到预设目标"

        except Exception as e:
            print(f"离线分析异常: {e}")
            return cv2.imread(image_path), f"分析异常: {e}"

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

    def update_sensor_ui(self, d, t, h, lat, lon, location_name=""):
        # 1. 更新文字标签
        self.lbl_dist.config(text=f"📏 {d} cm")
        self.lbl_temp.config(text=f"🌡️ {t} ℃")
        self.lbl_humi.config(text=f"💧 {h} %")
        self.lbl_lat.config(text=f"北纬(N): {lat}")
        self.lbl_lon.config(text=f"东经(E): {lon}")
        if hasattr(self, 'lbl_location') and self.lbl_location:
            if location_name:
                self.lbl_location.config(text=f"📍 {location_name}")
            else:
                self.lbl_location.config(text="📍 实际位置: --")

        # === 🔥 2. 更新动态折线图 ===
        try:
            # 将新数据追加到队列右侧，自动挤掉最老的数据
            self.temp_data.append(int(t))
            self.humi_data.append(int(h))

            # 更新线条的数据
            self.line_temp.set_ydata(self.temp_data)
            self.line_humi.set_ydata(self.humi_data)

            # 让 Matplotlib 重新绘制图表
            self.graph_canvas.draw_idle()
        except Exception as e:
            print(f"图表更新失败: {e}")

    def convert_nmea_to_decimal(self, nmea_str):
        """将 GPS 的 NMEA 格式 (ddmm.mmmmm) 转换为标准十进制度数"""
        try:
            if not nmea_str or float(nmea_str) == 0:
                return "0.000000"

            nmea_val = float(nmea_str)
            # 提取“度” (除以100取整，例如 3446.93 // 100 = 34)
            degrees = int(nmea_val / 100)
            # 提取“分” (原数字减去度数*100，例如 3446.93 - 3400 = 46.93)
            minutes = nmea_val - (degrees * 100)

            # 换算公式：度 + (分 / 60)
            decimal_degrees = degrees + (minutes / 60.0)

            # 返回保留 6 位小数的标准字符串
            return f"{decimal_degrees:.6f}"
        except Exception:
            return "0.000000"

    # === 🔥 逆地理编码：经纬度 → 实际地名 (高德 API) ===
    def reverse_geocode(self, lat, lon):
        """调用高德逆地理编码 API，返回格式化地址字符串"""
        try:
            url = f"https://restapi.amap.com/v3/geocode/regeo?key={self.amap_key}&location={lon},{lat}&extensions=base"
            resp = requests.get(url, timeout=3, proxies={"http": None, "https": None})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1" and data.get("regeocode"):
                    return data["regeocode"].get("formatted_address", "")
                else:
                    print(f"高德API返回异常: {data.get('info', 'unknown')}")
        except Exception as e:
            print(f"逆地理编码请求失败: {e}")
        return ""

    def resolve_location_name(self, lat_str, lon_str):
        """带缓存判断的逆地理编码入口：0.000000 跳过，相近坐标复用缓存"""
        try:
            lat_f = float(lat_str)
            lon_f = float(lon_str)
        except:
            return ""

        if lat_f == 0.0 and lon_f == 0.0:
            return ""

        # 坐标变化 < 0.0003°（约30m），直接复用上次结果
        if (abs(lat_f - self.last_resolved_lat) < 0.0003 and
                abs(lon_f - self.last_resolved_lon) < 0.0003 and
                self.last_location_name):
            return self.last_location_name

        # 后台线程请求 API，避免阻塞串口读取
        threading.Thread(target=self._do_geocode, args=(lat_f, lon_f), daemon=True).start()
        return self.last_location_name  # 首次先返回旧值，下次刷新时更新

    def _do_geocode(self, lat_f, lon_f):
        """实际执行 API 请求并更新缓存 + 刷新 UI"""
        addr = self.reverse_geocode(lat_f, lon_f)
        if addr:
            self.last_resolved_lat = lat_f
            self.last_resolved_lon = lon_f
            self.last_location_name = addr
            # 主动刷新 UI 上的位置标签
            if hasattr(self, 'lbl_location') and self.lbl_location:
                self.window.after(0, lambda: self.lbl_location.config(text=f"📍 {addr}"))

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

    # === 🔥 新增：微信告警推送 ===
    def send_wechat_alert(self, cls_name, conf, temp, humi):
        """调用 PushPlus API 发送微信通知"""
        pushplus_token = "bb07e55e4f3e404ea8b581a36c58c040"

        # 消息标题
        title = f"🚨 巡检终端警报：发现 {cls_name}！"

        # 消息正文（支持 HTML 格式，让在微信里看起来更好看）
        content = f"""
        <h3>🛡️ 智能城市巡检系统 实时告警</h3>
        <p><b>⚠️ 异常类型：</b>{cls_name}</p>
        <p><b>🎯 AI置信度：</b>{conf:.2f}</p>
        <p><b>🌡️ 现场温度：</b>{temp} ℃</p>
        <p><b>💧 现场湿度：</b>{humi} %</p>
        <p><b>⏰ 发现时间：</b>{time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        <hr>
        <p>请尽快登录上位机或派单处理！</p>
        """

        url = "http://www.pushplus.plus/send"
        data = {
            "token": pushplus_token,
            "title": title,
            "content": content,
            "template": "html"
        }

        try:
            # 发送请求
            response = requests.post(url, json=data, timeout=5)
            if response.status_code == 200:
                print(f"📲 微信告警推送成功: {cls_name}")
            else:
                print("📲 微信告警推送失败")
        except Exception as e:
            print(f"📲 推送发生异常: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartCarController(root, "STM32 & ESP32 智能巡检终端 V12.0")
    root.mainloop()