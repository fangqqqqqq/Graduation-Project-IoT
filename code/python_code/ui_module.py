import tkinter as tk
from tkinter import ttk
import cv2
import PIL.Image, PIL.ImageTk


def setup_ui(app):
    # === 1. 左侧：视频显示区域 ===
    video_frame = tk.Frame(app.window, bg="black", bd=2, relief=tk.SUNKEN)
    video_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)

    # 顶部状态栏
    status_frame = tk.Frame(video_frame, bg="#202020")
    status_frame.pack(fill=tk.X)
    app.video_status = tk.Label(status_frame, text="🔴 系统初始化...", bg="#202020", fg="white", font=("Arial", 10))
    app.video_status.pack(side=tk.LEFT, padx=5, pady=4)

    # 视频画布
    canvas_container = tk.Frame(video_frame, bg="black")
    canvas_container.pack(expand=True, fill=tk.BOTH)
    app.canvas = tk.Canvas(canvas_container, width=640, height=480, bg="#101010", bd=0, highlightthickness=0)
    app.canvas.pack(anchor=tk.CENTER, expand=True)

    # 底部刷新
    tk.Button(status_frame, text="🔄 重启视频流", command=app.refresh_video_stream,
              bg=app.style_cfg["btn_refresh"], fg="black", font=("Arial", 9, "bold"), bd=0, width=12).pack(
        side=tk.RIGHT, padx=5, pady=2)

    # === 2. 右侧：控制面板 (宽度保持 360) ===
    ctrl_panel = tk.Frame(app.window, bg=app.style_cfg["bg_panel"], width=360)
    ctrl_panel.pack(side=tk.RIGHT, fill=tk.Y, ipadx=10)

    # 标题 (加大字体)
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

    # 放大连接按钮
    app.btn_connect = tk.Button(conn_row, text="🔗 连接", command=app.toggle_connection,
                                bg=app.style_cfg["btn_normal"], fg="white", width=8, bd=0, font=("Arial", 10, "bold"))
    app.btn_connect.pack(side=tk.LEFT, padx=5)

    app.status_label = tk.Label(conn_box, text="状态: ❌ 断开", bg=app.style_cfg["bg_panel"], fg="#707070",
                                font=("Arial", 10))
    app.status_label.pack(side=tk.RIGHT, padx=5)

    # --- 模块2: 环境数据 ---
    sensor_box = create_group_box(app, ctrl_panel, "📊 环境监测")
    sensor_grid = tk.Frame(sensor_box, bg=app.style_cfg["bg_panel"])
    sensor_grid.pack(fill=tk.X, pady=2)

    app.lbl_dist = create_value_label(sensor_grid, "📏 --cm", 0, 0, app)
    app.lbl_temp = create_value_label(sensor_grid, "🌡️ --℃", 0, 1, app)
    app.lbl_humi = create_value_label(sensor_grid, "💧 --%", 0, 2, app)
    sensor_grid.columnconfigure(0, weight=1)
    sensor_grid.columnconfigure(1, weight=1)
    sensor_grid.columnconfigure(2, weight=1)

    # --- 模块3: 核心控制区 ---
    main_ctrl_box = create_group_box(app, ctrl_panel, "🎮 核心控制")

    # >> 3.1 小车运动 (WASD + QE)
    move_frame = tk.Frame(main_ctrl_box, bg=app.style_cfg["bg_panel"])
    move_frame.pack(pady=3)

    btn_w = 10

    # 第一排
    create_auto_release_btn(move_frame, "↺ 左旋", b'F', b'B', 0, 0, app, bg="#6a5acd", w=btn_w)
    create_auto_release_btn(move_frame, "⬆ 前进", b'@', b'B', 0, 1, app, w=btn_w)
    create_auto_release_btn(move_frame, "↻ 右旋", b'E', b'B', 0, 2, app, bg="#6a5acd", w=btn_w)

    # 第二排
    create_auto_release_btn(move_frame, "⬅ 左转", b'C', b'B', 1, 0, app, w=btn_w)
    tk.Button(move_frame, text="🛑 急停", command=app.stop_action,
              bg=app.style_cfg["btn_stop"], fg="white", width=btn_w, height=1, bd=0,
              font=("Arial", 10, "bold")).grid(row=1, column=1, padx=3, pady=3)
    create_auto_release_btn(move_frame, "➡ 右转", b'D', b'B', 1, 2, app, w=btn_w)

    # 第三排
    create_auto_release_btn(move_frame, "⬇ 后退", b'A', b'B', 2, 1, app, w=btn_w)

    ttk.Separator(main_ctrl_box, orient='horizontal').pack(fill='x', pady=5)

    # >> 3.2 硬件模式 & 云台
    hw_frame = tk.Frame(main_ctrl_box, bg=app.style_cfg["bg_panel"])
    hw_frame.pack(fill=tk.X, pady=2)

    mode_col = tk.Frame(hw_frame, bg=app.style_cfg["bg_panel"])
    mode_col.pack(side=tk.LEFT, padx=5, fill=tk.Y)
    tk.Button(mode_col, text="🛡️ 自动避障", command=lambda: app.send_cmd(b'H', "避障模式"),
              bg="#ffb86c", fg="black", width=14, bd=0, font=("Arial", 10, "bold"), pady=2).pack(pady=3)
    tk.Button(mode_col, text="🛤️ 黑线循迹", command=lambda: app.send_cmd(b'G', "循迹模式"),
              bg="#ffb86c", fg="black", width=14, bd=0, font=("Arial", 10, "bold"), pady=2).pack(pady=3)

    ptz_col = tk.Frame(hw_frame, bg=app.style_cfg["bg_panel"])
    ptz_col.pack(side=tk.RIGHT, padx=5, fill=tk.Y)
    create_auto_release_btn(ptz_col, "☁ 云台上升", b'R', b'B', 0, 0, app, w=12, grid=True)
    create_auto_release_btn(ptz_col, "☁ 云台下降", b'Q', b'B', 1, 0, app, w=12, grid=True)

    # --- 模块4: 上位机 AI ---
    ai_box = create_group_box(app, ctrl_panel, "🤖 AI 视觉")

    btn_ai_frame = tk.Frame(ai_box, bg=app.style_cfg["bg_panel"])
    btn_ai_frame.pack(fill=tk.X, pady=2)
    app.btn_ai = tk.Button(btn_ai_frame, text="👁️ 目标识别: 开", command=app.toggle_ai,
                           bg=app.style_cfg["btn_go"], fg="black", bd=0, font=("Arial", 10, "bold"), width=15)
    app.btn_ai.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    app.btn_auto = tk.Button(btn_ai_frame, text="🚀 自动巡逻", command=app.toggle_auto_patrol,
                             bg=app.style_cfg["btn_auto"], fg="black", bd=0, font=("Arial", 10, "bold"), width=15)
    app.btn_auto.pack(side=tk.RIGHT, padx=5, fill=tk.X, expand=True)

    light_frame = tk.Frame(ai_box, bg=app.style_cfg["bg_panel"])
    light_frame.pack(fill=tk.X, pady=2, padx=5)
    tk.Label(light_frame, text="💡 补光:", bg=app.style_cfg["bg_panel"], fg="white", font=("Arial", 10)).pack(
        side=tk.LEFT)
    app.light_scale = tk.Scale(light_frame, from_=0, to=255, orient=tk.HORIZONTAL,
                               bg=app.style_cfg["bg_panel"], fg="white", highlightthickness=0,
                               command=app.on_light_change)
    app.light_scale.set(0)
    app.light_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    app.btn_rotate = tk.Button(ai_box, text="🔄 画面旋转: 0°", command=app.toggle_rotation,
                               bg=app.style_cfg["btn_normal"], fg="white", bd=0, font=("Arial", 10))
    app.btn_rotate.pack(fill=tk.X, pady=2, padx=5)

    # --- 🔥 模块5: 通用模式识别 (本次新增核心) ---
    pattern_box = create_group_box(app, ctrl_panel, "🔍 通用模式识别")

    # 路径显示
    app.lbl_pattern_path = tk.Label(pattern_box, text="请先选择本地照片...", bg=app.style_cfg["bg_panel"], fg="gray",
                                    font=("Arial", 9), anchor="w")
    app.lbl_pattern_path.pack(fill=tk.X, pady=(2, 5), padx=5)

    # 按钮组
    pattern_btn_frame = tk.Frame(pattern_box, bg=app.style_cfg["bg_panel"])
    pattern_btn_frame.pack(fill=tk.X, padx=5)
    tk.Button(pattern_btn_frame, text="📂 上传照片", command=app.select_image, bg=app.style_cfg["btn_normal"],
              fg="white", bd=0, font=("Arial", 10)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
    tk.Button(pattern_btn_frame, text="🧠 分析模式", command=app.analyze_image, bg=app.style_cfg["btn_func"], fg="white",
              bd=0, font=("Arial", 10, "bold")).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

    # 结果显示
    app.lbl_pattern_result = tk.Label(pattern_box, text="分析结果: 等待上传", bg=app.style_cfg["bg_panel"],
                                      fg=app.style_cfg["accent"], font=("Arial", 10, "bold"), anchor="w",
                                      wraplength=320, justify="left")
    app.lbl_pattern_result.pack(fill=tk.X, pady=5, padx=5)

    # --- 模块6: 数据中心 (最底部) ---
    tk.Button(ctrl_panel, text="📊 历史数据中心", command=app.open_history_window,
              bg="#6272a4", fg="white", font=("Microsoft YaHei", 10, "bold"), height=2, bd=0).pack(fill=tk.X,
                                                                                                   side=tk.BOTTOM,
                                                                                                   pady=10)


# === 功能函数 ===
def create_auto_release_btn(parent, text, press_cmd, release_cmd, r, c, app, w=8, bg=None, grid=True):
    if bg is None: bg = app.style_cfg["btn_normal"]
    btn = tk.Button(parent, text=text, bg=bg, fg="white", width=w, height=1, bd=0, font=("Arial", 10, "bold"))
    if grid:
        btn.grid(row=r, column=c, padx=3, pady=3)
    else:
        btn.pack(pady=3)
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


# === 历史弹窗 (加入右键闭环管理) ===
class HistoryWindow:
    def __init__(self, master, db_manager):
        self.top = tk.Toplevel(master)
        self.top.title("数据中心 - 智能巡检业务闭环")
        self.top.geometry("1100x650")  # 加宽窗口适应新字段
        self.db = db_manager

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", rowheight=28, font=('Arial', 10))
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))

        tab_control = ttk.Notebook(self.top)
        self.tab1 = ttk.Frame(tab_control)
        tab_control.add(self.tab1, text='🌡️ 环境数据流')
        self.tab2 = ttk.Frame(tab_control)
        tab_control.add(self.tab2, text='📷 巡检异常工单')
        tab_control.pack(expand=1, fill="both")

        self.setup_sensor_tab()
        self.setup_detection_tab()
        tk.Button(self.top, text="🔄 刷新数据", command=self.refresh_data, bg="#50fa7b", font=("Arial", 11, "bold"),
                  height=2, bd=0).pack(fill=tk.X, side=tk.BOTTOM)

    def setup_sensor_tab(self):
        cols = ("ID", "批次", "时间", "距离(cm)", "温度(C)", "湿度(%)", "备注")
        self.tree1 = ttk.Treeview(self.tab1, columns=cols, show='headings')
        for col in cols:
            self.tree1.heading(col, text=col)
            w = 60 if col in ("ID", "批次") else 120
            self.tree1.column(col, width=w, anchor=tk.CENTER)
        self.tree1.pack(expand=True, fill='both', padx=10, pady=10)
        self.load_sensor_data()

    def setup_detection_tab(self):
        # 融合快照数据与状态机
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

        # 🔥 创建右键菜单
        self.popup_menu = tk.Menu(self.top, tearoff=0)
        self.popup_menu.add_command(label="✅ 标记为【已修复】", command=lambda: self.change_status("✅ 已修复"))
        self.popup_menu.add_command(label="⚠️ 标记为【误报】", command=lambda: self.change_status("⚠️ 误报"))
        self.popup_menu.add_separator()
        self.popup_menu.add_command(label="🔴 重置为【待处理】", command=lambda: self.change_status("🔴 待处理"))

        # 绑定右键点击事件 (Windows 通常是 <Button-3>)
        self.tree2.bind("<Button-3>", self.show_popup)

        self.load_detection_data()

    def show_popup(self, event):
        item = self.tree2.identify_row(event.y)
        if item:
            self.tree2.selection_set(item)  # 选中当前点击的行
            self.popup_menu.tk_popup(event.x_root, event.y_root)  # 弹出菜单

    def change_status(self, new_status):
        selected = self.tree2.selection()
        if not selected: return
        item = selected[0]
        record_values = self.tree2.item(item, 'values')
        record_id = record_values[0]  # 获取隐藏的 ID

        # 更新数据库
        self.db.update_detection_status(record_id, new_status)
        # 刷新表格
        self.load_detection_data()

    def load_sensor_data(self):
        for row in self.tree1.get_children(): self.tree1.delete(row)
        for row in self.db.fetch_sensor_logs(): self.tree1.insert("", tk.END, values=row)

    def load_detection_data(self):
        for row in self.tree2.get_children(): self.tree2.delete(row)
        for row in self.db.fetch_detection_logs():
            # 格式化置信度
            formatted_row = list(row)
            formatted_row[5] = f"{float(row[5]):.2f}"
            self.tree2.insert("", tk.END, values=formatted_row)

    def refresh_data(self):
        self.load_sensor_data()
        self.load_detection_data()