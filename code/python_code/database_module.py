import sqlite3
import pymysql
import datetime
import threading


class DatabaseManager:
    def __init__(self):
        # === 💾 1. 本地边缘端配置 (SQLite 容灾备份) ===
        self.local_db_name = "patrol_edge_backup.db"

        # === ☁️ 2. 远端云中心配置 (阿里云 MySQL 实时同步) ===
        self.cloud_host = "rm-2ze79o40931rt4e007o.mysql.rds.aliyuncs.com"
        self.cloud_port = 3306
        self.cloud_user = "fangq"
        self.cloud_pwd = "1197120771Fgq@"
        self.cloud_db_name = "patrol_cloud_db"

        # 启动时初始化双端数据库表结构
        self.init_local_db()
        self.init_cloud_db()

    # ==========================================
    # 🛠️ 数据库初始化模块
    # ==========================================
    def init_local_db(self):
        """初始化本地 SQLite 数据库"""
        try:
            conn = sqlite3.connect(self.local_db_name, check_same_thread=False)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS patrol_sessions (session_id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TEXT, end_time TEXT, status TEXT DEFAULT '巡逻中')''')
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS sensor_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, timestamp TEXT, distance REAL, temperature INTEGER, humidity INTEGER, note TEXT, FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id))''')
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS detection_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, timestamp TEXT, object_type TEXT, confidence REAL, image_path TEXT, snapshot_temp INTEGER, snapshot_humi INTEGER, status TEXT DEFAULT '🔴 待处理', FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id))''')
            conn.commit()
            conn.close()
            print("💾 本地边缘数据库就绪！")
        except Exception as e:
            print(f"本地DB初始化失败: {e}")

    def get_cloud_conn(self):
        """获取云端连接"""
        return pymysql.connect(host=self.cloud_host, port=self.cloud_port, user=self.cloud_user,
                               password=self.cloud_pwd, database=self.cloud_db_name, charset='utf8mb4', autocommit=True,
                               connect_timeout=3)

    def init_cloud_db(self):
        """初始化云端 MySQL 数据库"""
        try:
            conn = self.get_cloud_conn()
            cursor = conn.cursor()
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS patrol_sessions (session_id INT PRIMARY KEY, start_time DATETIME, end_time DATETIME, status VARCHAR(50) DEFAULT '巡逻中')''')
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS sensor_logs (id INT PRIMARY KEY AUTO_INCREMENT, session_id INT, timestamp DATETIME, distance FLOAT, temperature INT, humidity INT, note VARCHAR(255), FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id) ON DELETE CASCADE)''')
            cursor.execute(
                '''CREATE TABLE IF NOT EXISTS detection_logs (id INT PRIMARY KEY AUTO_INCREMENT, session_id INT, timestamp DATETIME, object_type VARCHAR(50), confidence FLOAT, image_path VARCHAR(255), snapshot_temp INT, snapshot_humi INT, status VARCHAR(50) DEFAULT '🔴 待处理', FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id) ON DELETE CASCADE)''')
            conn.close()
            print("☁️ 阿里云数据库同步通道就绪！")
        except Exception as e:
            print(f"⚠️ 云端通道未连接 (系统将处于离线边缘模式): {e}")

    # ==========================================
    # 🚀 业务生命周期 (以本地ID为准，强制云端同步)
    # ==========================================
    def start_session(self):
        local_id = None
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 强制写入本地 (生成唯一 ID)
        try:
            conn = sqlite3.connect(self.local_db_name, check_same_thread=False, timeout=5)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO patrol_sessions (start_time) VALUES (?)", (now,))
            local_id = cursor.lastrowid
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"启动任务(本地)失败: {e}")

        # 2. 尝试同步到云端 (强制使用本地生成的 ID，确保双端外键一致)
        if local_id is not None:
            try:
                conn = self.get_cloud_conn()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO patrol_sessions (session_id, start_time) VALUES (%s, %s)", (local_id, now))
                conn.close()
            except Exception as e:
                print("⚠️ 任务云端同步失败 (离线容灾生效)")

        return local_id

    def end_session(self, session_id):
        if not session_id: return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 本地更新
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute("UPDATE patrol_sessions SET end_time = ?, status = '已结束' WHERE session_id = ?",
                         (now, session_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 云端同步
        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute("UPDATE patrol_sessions SET end_time = %s, status = '已结束' WHERE session_id = %s",
                                  (now, session_id))
            conn.close()
        except Exception:
            pass

    # ==========================================
    # 📡 数据双写引擎 (Dual-Write Engine)
    # ==========================================
    def insert_sensor_data(self, session_id, dist, temp, humi, note="定时记录"):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 1. 本地备份
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute(
                "INSERT INTO sensor_logs (session_id, timestamp, distance, temperature, humidity, note) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, now, dist, temp, humi, note))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 2. 云端同步
        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute(
                "INSERT INTO sensor_logs (session_id, timestamp, distance, temperature, humidity, note) VALUES (%s, %s, %s, %s, %s, %s)",
                (session_id, now, dist, temp, humi, note))
            conn.close()
        except Exception:
            pass

    def insert_detection_event(self, session_id, obj_type, conf, img_path, temp, humi):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 1. 本地留证
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=10)
            conn.execute(
                "INSERT INTO detection_logs (session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, now, obj_type, conf, img_path, temp, humi))
            conn.commit()
            conn.close()
            print(f"✅ [边缘端] 证据已保存: {obj_type}")
        except Exception as e:
            print(f"❌ [边缘端] 写入失败: {e}")

        # 2. 实时上云
        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute(
                "INSERT INTO detection_logs (session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (session_id, now, obj_type, conf, img_path, temp, humi))
            conn.close()
            print(f"☁️ [云端] 证据已同步: {obj_type}")
        except Exception as e:
            print(f"⚠️ [云端] 同步延迟 (断网不影响本地): {e}")

    # ==========================================
    # 🔄 UI 状态更新与读取 (优先读取本地，保证极速响应)
    # ==========================================
    def update_detection_status(self, record_id, new_status):
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute("UPDATE detection_logs SET status = ? WHERE id = ?", (new_status, record_id))
            conn.commit()
            conn.close()
        except Exception:
            pass
        # 注：为了简化毕设逻辑，UI状态更新暂不同步云端，以免双端冲突，以本地指挥台为准。

    def fetch_sensor_logs(self, limit=50):
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, session_id, timestamp, distance, temperature, humidity, note FROM sensor_logs ORDER BY id DESC LIMIT ?',
                (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except:
            return []

    def fetch_detection_logs(self, limit=50):
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, session_id, status, timestamp, object_type, confidence, snapshot_temp, snapshot_humi, image_path FROM detection_logs ORDER BY id DESC LIMIT ?',
                (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except:
            return []