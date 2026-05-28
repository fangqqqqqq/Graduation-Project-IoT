import tkinter as tk
from tkinter import ttk, filedialog
import cv2
import PIL.Image, PIL.ImageTk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import collections
import glob  # 🔥 新增：用于扫描本地文件
import os  # 🔥 新增


def setup_ui(app):
    # === 1. 左侧：视频显示区域 ===
    # 【完美解决黑框】：让画布背景色和主背景色 #1e1e2e 彻底融为一体
    video_frame = tk.Frame(app.window, bg=app.style_cfg["bg_main"], bd=0)
    video_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)

    # 顶部状态栏
    status_frame = tk.Frame(video_frame, bg=app.style_cfg["bg_panel"], bd=1, relief=tk.SOLID)
    status_frame.pack(fill=tk.X, pady=(0, 10))
    app.video_status = tk.Label(status_frame, text="🔴 系统初始化...", bg=app.style_cfg["bg_panel"], fg="white",
                                font=("Arial", 10))
    app.video_status.pack(side=tk.LEFT, padx=5, pady=4)

    # 底部刷新
    tk.Button(status_frame, text="🔄 重启视频流", command=app.refresh_video_stream,
              bg=app.style_cfg["btn_refresh"], fg="black", font=("Arial", 9, "bold"), bd=0, width=12,
              cursor="hand2").pack(
        side=tk.RIGHT, padx=5, pady=2)

    # 视频画布 (彻底去边框，背景色同主色)
    canvas_container = tk.Frame(video_frame, bg=app.style_cfg["bg_main"])
    canvas_container.pack(expand=True, fill=tk.BOTH)
    app.canvas = tk.Canvas(canvas_container, width=640, height=480, bg=app.style_cfg["bg_main"], bd=0,
                           highlightthickness=0)
    app.canvas.pack(anchor=tk.CENTER, expand=True)

    # === 2. 右侧：控制面板 (宽度保持 360) ===
    ctrl_panel = tk.Frame(app.window, bg=app.style_cfg["bg_panel"], width=360)
    ctrl_panel.pack(side=tk.RIGHT, fill=tk.Y, ipadx=10)

    tk.Label(ctrl_panel, text="🛡️ 智能巡检终端 Pro", bg=app.style_cfg["bg_panel"],
             fg=app.style_cfg["accent"], font=("Microsoft YaHei", 18, "bold")).pack(pady=(15, 10))

    # --- 模块1: 系统连接 ---
    conn_box = create_group_box(app, ctrl_panel, "📡 连接配置")
    conn_row = tk.Frame(conn_box, bg=app.style_cfg["bg_panel"])
    conn_row.pack(fill=tk.X, pady=2)

    tk.Label(conn_row, text="端口:", bg=app.style_cfg["bg_panel"], fg="white", font=("Arial", 11)).pack(side=tk.LEFT)
    app.port_entry = tk.Entry(conn_row, width=8, bg="#404040", fg="white", insertbackground="white", font=("Arial", 10))
    app.port_entry.insert(0, app.default_com)
    app.port_entry.pack(side=tk.LEFT, padx=5)

    app.btn_connect = tk.Button(conn_row, text="🔗 连接", command=app.toggle_connection,
                                bg=app.style_cfg["btn_normal"], fg="white", width=8, bd=0, font=("Arial", 10, "bold"),
                                cursor="hand2")
    app.btn_connect.pack(side=tk.LEFT, padx=5)

    app.status_label = tk.Label(conn_box, text="状态: ❌ 断开", bg=app.style_cfg["bg_panel"], fg="#707070",
                                font=("Arial", 10))
    app.status_label.pack(side=tk.RIGHT, padx=5)

    # --- 模块2: 环境数据 (动态折线图) ---
    sensor_box = create_group_box(app, ctrl_panel, "📊 实时环境监测")
    sensor_grid = tk.Frame(sensor_box, bg=app.style_cfg["bg_panel"])
    sensor_grid.pack(fill=tk.X, pady=2)
    app.lbl_dist = create_value_label(sensor_grid, "📏 --cm", 0, 0, app)
    app.lbl_temp = create_value_label(sensor_grid, "🌡️ --℃", 0, 1, app)
    app.lbl_humi = create_value_label(sensor_grid, "💧 --%", 0, 2, app)
    sensor_grid.columnconfigure(0, weight=1);
    sensor_grid.columnconfigure(1, weight=1);
    sensor_grid.columnconfigure(2, weight=1)

    chart_frame = tk.Frame(sensor_box, bg=app.style_cfg["bg_panel"], height=150)
    chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    app.temp_data = collections.deque([0] * 30, maxlen=30)
    app.humi_data = collections.deque([0] * 30, maxlen=30)
    app.fig = Figure(figsize=(4, 1.8), dpi=100, facecolor=app.style_cfg["bg_panel"])
    app.fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.15)
    app.ax = app.fig.add_subplot(111)
    app.ax.set_facecolor("#1e1e2e")
    app.ax.tick_params(colors='white', labelsize=8)
    for spine in app.ax.spines.values(): spine.set_color('#44475a')
    app.line_temp, = app.ax.plot(app.temp_data, color="#ff5555", label="Temp(C)", linewidth=2)
    app.line_humi, = app.ax.plot(app.humi_data, color="#8be9fd", label="Humi(%)", linewidth=2)
    app.ax.legend(loc='upper right', fontsize=7, facecolor="#282a36", labelcolor="white")
    app.ax.set_ylim(-10, 100)
    app.graph_canvas = FigureCanvasTkAgg(app.fig, master=chart_frame)
    app.graph_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # --- 模块2.5: GPS定位面板 ---
    gps_box = create_group_box(app, ctrl_panel, "📍 实时定位")
    gps_grid = tk.Frame(gps_box, bg=app.style_cfg["bg_panel"])
    gps_grid.pack(fill=tk.X, pady=2)
    app.lbl_lat = create_value_label(gps_grid, "北纬(N): --", 0, 0, app)
    app.lbl_lon = create_value_label(gps_grid, "东经(E): --", 0, 1, app)
    gps_grid.columnconfigure(0, weight=1);
    gps_grid.columnconfigure(1, weight=1)

    # 实际位置显示行（占满两列）
    app.lbl_location = tk.Label(gps_box, text="📍 实际位置: --", bg=app.style_cfg["bg_panel"],
                                fg="#f1fa8c", font=("Arial", 10), anchor="w")
    app.lbl_location.pack(fill=tk.X, padx=5, pady=(2, 5))

    # --- 模块3: 核心控制区 ---
    main_ctrl_box = create_group_box(app, ctrl_panel, "🎮 核心控制")
    move_frame = tk.Frame(main_ctrl_box, bg=app.style_cfg["bg_panel"])
    move_frame.pack(pady=3)
    btn_w = 10
    create_auto_release_btn(move_frame, "↺ 左旋", b'F', b'B', 0, 0, app, bg="#6272a4", w=btn_w)
    create_auto_release_btn(move_frame, "⬆ 前进", b'@', b'B', 0, 1, app, w=btn_w)
    create_auto_release_btn(move_frame, "↻ 右旋", b'E', b'B', 0, 2, app, bg="#6272a4", w=btn_w)
    create_auto_release_btn(move_frame, "⬅ 左转", b'C', b'B', 1, 0, app, w=btn_w)

    btn_stop = tk.Button(move_frame, text="🛑 急停", command=app.stop_action,
                         bg=app.style_cfg["btn_stop"], activebackground="#ff7777", fg="white", activeforeground="white",
                         width=btn_w, height=1, bd=0, font=("Arial", 10, "bold"), cursor="hand2")
    btn_stop.grid(row=1, column=1, padx=3, pady=3)
    btn_stop.bind("<Enter>", lambda e: btn_stop.config(bg="#ff7777"))
    btn_stop.bind("<Leave>", lambda e: btn_stop.config(bg=app.style_cfg["btn_stop"]))

    create_auto_release_btn(move_frame, "➡ 右转", b'D', b'B', 1, 2, app, w=btn_w)
    create_auto_release_btn(move_frame, "⬇ 后退", b'A', b'B', 2, 1, app, w=btn_w)

    ttk.Separator(main_ctrl_box, orient='horizontal').pack(fill='x', pady=5)
    hw_frame = tk.Frame(main_ctrl_box, bg=app.style_cfg["bg_panel"])
    hw_frame.pack(fill=tk.X, pady=2)
    mode_col = tk.Frame(hw_frame, bg=app.style_cfg["bg_panel"])
    mode_col.pack(side=tk.LEFT, padx=5, fill=tk.Y)

    btn_avoid = tk.Button(mode_col, text="🛡️ 自动避障", command=lambda: app.send_cmd(b'H', "避障模式"), bg="#ffb86c",
                          activebackground="#ffc98a", fg="black", width=14, bd=0, font=("Arial", 10, "bold"),
                          cursor="hand2", pady=2)
    btn_avoid.pack(pady=3)
    btn_avoid.bind("<Enter>", lambda e: btn_avoid.config(bg="#ffc98a"))
    btn_avoid.bind("<Leave>", lambda e: btn_avoid.config(bg="#ffb86c"))

    btn_track = tk.Button(mode_col, text="🛤️ 黑线循迹", command=lambda: app.send_cmd(b'G', "循迹模式"), bg="#ffb86c",
                          activebackground="#ffc98a", fg="black", width=14, bd=0, font=("Arial", 10, "bold"),
                          cursor="hand2", pady=2)
    btn_track.pack(pady=3)
    btn_track.bind("<Enter>", lambda e: btn_track.config(bg="#ffc98a"))
    btn_track.bind("<Leave>", lambda e: btn_track.config(bg="#ffb86c"))

    ptz_col = tk.Frame(hw_frame, bg=app.style_cfg["bg_panel"])
    ptz_col.pack(side=tk.RIGHT, padx=5, fill=tk.Y)
    create_auto_release_btn(ptz_col, "☁ 云台上升", b'R', b'B', 0, 0, app, w=12, grid=True)
    create_auto_release_btn(ptz_col, "☁ 云台下降", b'Q', b'B', 1, 0, app, w=12, grid=True)

    # --- 模块4: 上位机 AI ---
    ai_box = create_group_box(app, ctrl_panel, "🤖 AI 视觉")
    btn_ai_frame = tk.Frame(ai_box, bg=app.style_cfg["bg_panel"])
    btn_ai_frame.pack(fill=tk.X, pady=2)
    app.btn_ai = tk.Button(btn_ai_frame, text="👁️ 目标识别: 开", command=app.toggle_ai, bg=app.style_cfg["btn_go"],
                           activebackground="#6afb8e", fg="black", bd=0, font=("Arial", 10, "bold"), cursor="hand2",
                           width=15)
    app.btn_ai.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    app.btn_auto = tk.Button(btn_ai_frame, text="🚀 自动巡逻", command=app.toggle_auto_patrol,
                             bg=app.style_cfg["btn_auto"], activebackground="#ffc98a", fg="black", bd=0,
                             font=("Arial", 10, "bold"), cursor="hand2", width=15)
    app.btn_auto.pack(side=tk.RIGHT, padx=5, fill=tk.X, expand=True)

    light_frame = tk.Frame(ai_box, bg=app.style_cfg["bg_panel"])
    light_frame.pack(fill=tk.X, pady=2, padx=5)
    tk.Label(light_frame, text="💡 补光:", bg=app.style_cfg["bg_panel"], fg="white", font=("Arial", 10)).pack(
        side=tk.LEFT)
    app.light_scale = tk.Scale(light_frame, from_=0, to=255, orient=tk.HORIZONTAL, bg=app.style_cfg["bg_panel"],
                               fg="white", highlightthickness=0, command=app.on_light_change)
    app.light_scale.set(0)
    app.light_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # =========================================================
    # 🔥 新增入口：独立的高级图像分析工作台
    # =========================================================
    tk.Button(ctrl_panel, text="🔍 开启离线图像分析工作台", command=app.open_image_analysis_window,
              bg="#bd93f9", activebackground="#d7bdf9", fg="black", font=("Microsoft YaHei", 11, "bold"), height=2,
              bd=0, cursor="hand2").pack(fill=tk.X, pady=(15, 0), padx=5)

    # 历史数据中心
    tk.Button(ctrl_panel, text="📊 历史数据中心", command=app.open_history_window,
              bg="#6272a4", activebackground="#7888b4", fg="white", font=("Microsoft YaHei", 10, "bold"), height=2,
              bd=0, cursor="hand2").pack(fill=tk.X, side=tk.BOTTOM, pady=10)


# === 功能函数 ===
def create_auto_release_btn(parent, text, press_cmd, release_cmd, r, c, app, w=8, bg=None, grid=True):
    if bg is None: bg = app.style_cfg["btn_normal"]

    def lighten_color(hex_color):
        try:
            hex_color = hex_color.lstrip('#')
            r_c, g_c, b_c = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            return f'#{min(r_c + 40, 255):02x}{min(g_c + 40, 255):02x}{min(b_c + 40, 255):02x}'
        except:
            return "#ffffff"

    hover_bg = lighten_color(bg)
    btn = tk.Button(parent, text=text, bg=bg, activebackground=hover_bg, fg="white",
                    activeforeground="white", width=w, height=1, bd=0, font=("Arial", 10, "bold"), cursor="hand2")
    if grid:
        btn.grid(row=r, column=c, padx=4, pady=4)
    else:
        btn.pack(pady=4)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    btn.bind('<ButtonPress-1>', lambda event: app.send_cmd(press_cmd, f"开始: {text}"))
    btn.bind('<ButtonRelease-1>', lambda event: app.send_cmd(release_cmd, "停止"))
    return btn


def create_group_box(app, parent, title):
    frame = tk.LabelFrame(parent, text=title, bg=app.style_cfg["bg_panel"], fg=app.style_cfg["text_dim"],
                          font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
    frame.pack(fill=tk.X, padx=5, pady=2, ipady=1)
    return frame


def create_value_label(parent, text, r, c, app):
    lbl = tk.Label(parent, text=text, bg=app.style_cfg["bg_panel"], fg=app.style_cfg["accent"],
                   font=("Arial", 11, "bold"), anchor="center")
    lbl.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
    return lbl


# =========================================================
# 🔥 全新子窗口：高级图像分析中心
# =========================================================
class ImageAnalysisWindow:
    def __init__(self, master, app):
        self.top = tk.Toplevel(master)
        self.top.title("🔍 智能巡检 - 离线图像高级分析中心")
        self.top.geometry("1050x650")
        self.top.configure(bg=app.style_cfg["bg_main"])
        self.app = app
        self.current_image_path = None

        # 左右分栏设计
        left_frame = tk.Frame(self.top, bg=app.style_cfg["bg_main"])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        right_frame = tk.Frame(self.top, bg=app.style_cfg["bg_panel"], width=320)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # === 左侧：超大图像预览区 ===
        tk.Label(left_frame, text="🖼️ 图像预览", bg=app.style_cfg["bg_main"], fg="white",
                 font=("Microsoft YaHei", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.img_canvas_frame = tk.Frame(left_frame, bg="black", bd=2, relief=tk.SUNKEN)
        self.img_canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.img_canvas_frame, bg="#101010", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # === 右侧：高级控制台 ===
        tk.Label(right_frame, text="⚙️ 分析参数设置", bg=app.style_cfg["bg_panel"], fg=app.style_cfg["accent"],
                 font=("Microsoft YaHei", 14, "bold")).pack(pady=15)

        # 1. 动态 AI 模型选择 (自动扫描当前目录下的 .pt 文件)
        tk.Label(right_frame, text="🧠 AI 模型选择 (.pt):", bg=app.style_cfg["bg_panel"], fg="white",
                 font=("Arial", 10)).pack(
            anchor="w", padx=15, pady=(10, 2))

        # 使用 glob 自动查找目录下所有的 .pt 文件
        pt_files = glob.glob("*.pt")
        if not pt_files:
            pt_files = ["未找到模型文件"]

        self.model_var = tk.StringVar(value=pt_files[0])
        self.model_combo = ttk.Combobox(right_frame, textvariable=self.model_var, values=pt_files, state="readonly")
        self.model_combo.pack(fill=tk.X, padx=15, pady=5)

        # 2. 独立类别的置信度滑块
        tk.Label(right_frame, text="🎚️ 独立类别置信度 (Confidence):", bg=app.style_cfg["bg_panel"], fg="white",
                 font=("Arial", 10)).pack(anchor="w", padx=15, pady=(20, 5))

        self.sliders = {}
        for cls_name, current_val in app.class_thresholds.items():
            row = tk.Frame(right_frame, bg=app.style_cfg["bg_panel"])
            row.pack(fill=tk.X, padx=15, pady=5)
            tk.Label(row, text=cls_name.upper(), bg=app.style_cfg["bg_panel"], fg="#8be9fd", width=10, anchor="w").pack(
                side=tk.LEFT)

            var = tk.DoubleVar(value=current_val)
            scale = tk.Scale(row, variable=var, from_=0.01, to=0.99, resolution=0.01, orient=tk.HORIZONTAL,
                             bg=app.style_cfg["bg_panel"], fg="white", highlightthickness=0, length=120)
            scale.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            self.sliders[cls_name] = var

        # 3. 核心按钮区
        btn_frame = tk.Frame(right_frame, bg=app.style_cfg["bg_panel"])
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        self.lbl_status = tk.Label(btn_frame, text="状态: 等待上传照片...", bg=app.style_cfg["bg_panel"], fg="gray",
                                   font=("Arial", 10), wraplength=280)
        self.lbl_status.pack(pady=10)

        tk.Button(btn_frame, text="📂 1. 上传本地照片", command=self.upload_img, bg=app.style_cfg["btn_normal"],
                  fg="white", font=("Microsoft YaHei", 11), bd=0, height=2, cursor="hand2").pack(fill=tk.X, padx=15,
                                                                                                 pady=5)
        tk.Button(btn_frame, text="🚀 2. 开始 AI 分析", command=self.analyze, bg=app.style_cfg["btn_func"], fg="white",
                  font=("Microsoft YaHei", 12, "bold"), bd=0, height=2, cursor="hand2").pack(fill=tk.X, padx=15, pady=5)

    def upload_img(self):
        file_path = filedialog.askopenfilename(title="选择需要分析的照片",
                                               filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp")])
        if file_path:
            self.current_image_path = file_path
            self.lbl_status.config(text="状态: 图片已加载，准备就绪", fg=self.app.style_cfg["btn_go"])
            self.show_image_on_canvas(file_path)

    def show_image_on_canvas(self, path):
        # 动态缩放图片以适应 Canvas
        img = PIL.Image.open(path)
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:  # 如果窗口还没渲染完
            canvas_w, canvas_h = 700, 500

        img.thumbnail((canvas_w, canvas_h), PIL.Image.LANCZOS)
        self.tk_img = PIL.ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        # 居中显示
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor=tk.CENTER, image=self.tk_img)

    def analyze(self):
        # 把收集到的 UI 数据传给 app 的核心逻辑去处理
        if not self.current_image_path:
            self.lbl_status.config(text="⚠️ 错误: 请先上传照片", fg="red")
            return

        # 读取各个类别的最新阈值
        new_thresholds = {cls: var.get() for cls, var in self.sliders.items()}
        selected_model = self.model_var.get()

        self.lbl_status.config(text="状态: 正在推理中...", fg="yellow")
        self.top.update()

        # 调用核心推演函数 (它会返回标注好的新图片和结果文字)
        annotated_img, result_text = self.app.perform_offline_analysis(self.current_image_path, selected_model,
                                                                       new_thresholds)

        self.lbl_status.config(text=f"分析结果: {result_text}", fg="#50fa7b")

        # 渲染 AI 标注后的图片
        annotated_img_rgb = cv2.cvtColor(annotated_img, cv2.COLOR_BGR2RGB)
        img_pil = PIL.Image.fromarray(annotated_img_rgb)
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_pil.thumbnail((canvas_w, canvas_h), PIL.Image.LANCZOS)
        self.tk_img = PIL.ImageTk.PhotoImage(img_pil)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor=tk.CENTER, image=self.tk_img)


# === 历史弹窗代码保持不变 ===
class HistoryWindow:
    def __init__(self, master, db_manager):
        self.top = tk.Toplevel(master)
        self.top.title("数据中心 - 智能巡检业务闭环")
        self.top.geometry("1100x650")
        self.db = db_manager

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", rowheight=28, font=('Arial', 10))
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))

        tab_control = ttk.Notebook(self.top)
        self.tab1 = ttk.Frame(tab_control)
        tab_control.add(self.tab1, text='🌡️ 环境定位数据流')
        self.tab2 = ttk.Frame(tab_control)
        tab_control.add(self.tab2, text='📷 巡检异常工单')
        tab_control.pack(expand=1, fill="both")

        self.setup_sensor_tab()
        self.setup_detection_tab()
        tk.Button(self.top, text="🔄 刷新数据", command=self.refresh_data, bg="#50fa7b", font=("Arial", 11, "bold"),
                  height=2, bd=0, cursor="hand2").pack(fill=tk.X, side=tk.BOTTOM)

    def setup_sensor_tab(self):
        cols = ("ID", "批次", "时间", "距离(cm)", "温度(C)", "湿度(%)", "纬度", "经度", "实际位置", "备注")
        self.tree1 = ttk.Treeview(self.tab1, columns=cols, show='headings')
        for col in cols:
            self.tree1.heading(col, text=col)
            if col == "实际位置":
                w = 200
            elif col in ("ID", "批次"):
                w = 50
            else:
                w = 100
            self.tree1.column(col, width=w, anchor=tk.CENTER)
        self.tree1.pack(expand=True, fill='both', padx=10, pady=10)
        self.load_sensor_data()

    def setup_detection_tab(self):
        cols = ("ID", "批次", "处理状态", "发现时间", "目标类型", "置信度", "当时温度", "当时湿度", "留证路径")
        self.tree2 = ttk.Treeview(self.tab2, columns=cols, show='headings')
        for col in cols:
            self.tree2.heading(col, text=col)
            if col in ("ID", "批次"):
                w = 50
            elif col == "处理状态":
                w = 100
            elif col == "留证路径":
                w = 200
            else:
                w = 100
            self.tree2.column(col, width=w, anchor=tk.CENTER)
        self.tree2.pack(expand=True, fill='both', padx=10, pady=10)
        self.popup_menu = tk.Menu(self.top, tearoff=0)
        self.popup_menu.add_command(label="✅ 标记为【已修复】", command=lambda: self.change_status("✅ 已修复"))
        self.popup_menu.add_command(label="⚠️ 标记为【误报】", command=lambda: self.change_status("⚠️ 误报"))
        self.popup_menu.add_separator()
        self.popup_menu.add_command(label="🔴 重置为【待处理】", command=lambda: self.change_status("🔴 待处理"))
        self.tree2.bind("<Button-3>", self.show_popup)
        self.load_detection_data()

    def show_popup(self, event):
        item = self.tree2.identify_row(event.y)
        if item:
            self.tree2.selection_set(item)
            self.popup_menu.tk_popup(event.x_root, event.y_root)

    def change_status(self, new_status):
        selected = self.tree2.selection()
        if not selected: return
        item = selected[0]
        record_values = self.tree2.item(item, 'values')
        record_id = record_values[0]
        self.db.update_detection_status(record_id, new_status)
        self.load_detection_data()

    def load_sensor_data(self):
        for row in self.tree1.get_children(): self.tree1.delete(row)
        for row in self.db.fetch_sensor_logs(): self.tree1.insert("", tk.END, values=row)

    def load_detection_data(self):
        for row in self.tree2.get_children(): self.tree2.delete(row)
        for row in self.db.fetch_detection_logs():
            formatted_row = list(row)
            formatted_row[5] = f"{float(row[5]):.2f}"
            self.tree2.insert("", tk.END, values=formatted_row)

    def refresh_data(self):
        self.load_sensor_data()
        self.load_detection_data()