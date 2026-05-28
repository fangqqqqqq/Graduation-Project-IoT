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
            # 巡逻会话表
            cursor.execute('''CREATE TABLE IF NOT EXISTS patrol_sessions (
                                session_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                start_time TEXT, 
                                end_time TEXT, 
                                status TEXT DEFAULT '巡逻中')''')

            # 传感器日志表 - 已新增经纬度字段
            cursor.execute('''CREATE TABLE IF NOT EXISTS sensor_logs (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                session_id INTEGER,
                                timestamp TEXT,
                                distance REAL,
                                temperature INTEGER,
                                humidity INTEGER,
                                latitude TEXT,
                                longitude TEXT,
                                location_name TEXT,
                                note TEXT,
                                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id))''')

            # AI 检测日志表
            cursor.execute('''CREATE TABLE IF NOT EXISTS detection_logs (
                                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                session_id INTEGER, 
                                timestamp TEXT, 
                                object_type TEXT, 
                                confidence REAL, 
                                image_path TEXT, 
                                snapshot_temp INTEGER, 
                                snapshot_humi INTEGER, 
                                status TEXT DEFAULT '🔴 待处理', 
                                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id))''')
            # 兼容旧表：补增 location_name 列
            try:
                cursor.execute("ALTER TABLE sensor_logs ADD COLUMN location_name TEXT")
            except:
                pass  # 列已存在则忽略
            conn.commit()
            conn.close()
            print("💾 本地边缘数据库就绪（已更新经纬度支持）！")
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
            cursor.execute('''CREATE TABLE IF NOT EXISTS patrol_sessions (
                                session_id INT PRIMARY KEY, 
                                start_time DATETIME, 
                                end_time DATETIME, 
                                status VARCHAR(50) DEFAULT '巡逻中')''')

            # 云端表结构同步更新
            cursor.execute('''CREATE TABLE IF NOT EXISTS sensor_logs (
                                id INT PRIMARY KEY AUTO_INCREMENT,
                                session_id INT,
                                timestamp DATETIME,
                                distance FLOAT,
                                temperature INT,
                                humidity INT,
                                latitude VARCHAR(50),
                                longitude VARCHAR(50),
                                location_name VARCHAR(255),
                                note VARCHAR(255),
                                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id) ON DELETE CASCADE)''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS detection_logs (
                                id INT PRIMARY KEY AUTO_INCREMENT, 
                                session_id INT, 
                                timestamp DATETIME, 
                                object_type VARCHAR(50), 
                                confidence FLOAT, 
                                image_path VARCHAR(255), 
                                snapshot_temp INT, 
                                snapshot_humi INT, 
                                status VARCHAR(50) DEFAULT '🔴 待处理', 
                                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id) ON DELETE CASCADE)''')
            conn.close()
            print("☁️ 阿里云数据库同步通道就绪！")
        except Exception as e:
            print(f"⚠️ 云端通道未连接 (系统将处于离线边缘模式): {e}")

    # ==========================================
    # 🚀 业务生命周期
    # ==========================================
    def start_session(self):
        local_id = None
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn = sqlite3.connect(self.local_db_name, check_same_thread=False, timeout=5)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO patrol_sessions (start_time) VALUES (?)", (now,))
            local_id = cursor.lastrowid
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"启动任务(本地)失败: {e}")

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

        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute("UPDATE patrol_sessions SET end_time = ?, status = '已结束' WHERE session_id = ?",
                         (now, session_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute("UPDATE patrol_sessions SET end_time = %s, status = '已结束' WHERE session_id = %s",
                                  (now, session_id))
            conn.close()
        except Exception:
            pass

    # ==========================================
    # 📡 数据双写引擎 - 已更新以支持 GPS 数据
    # ==========================================
    def insert_sensor_data(self, session_id, dist, temp, humi, lat, lon, location_name="", note="定时记录"):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 1. 本地备份
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute(
                "INSERT INTO sensor_logs (session_id, timestamp, distance, temperature, humidity, latitude, longitude, location_name, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, now, dist, temp, humi, lat, lon, location_name, note))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"本地数据插入失败: {e}")

        # 2. 云端同步
        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute(
                "INSERT INTO sensor_logs (session_id, timestamp, distance, temperature, humidity, latitude, longitude, location_name, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (session_id, now, dist, temp, humi, lat, lon, location_name, note))
            conn.close()
        except Exception:
            pass

    def insert_detection_event(self, session_id, obj_type, conf, img_path, temp, humi):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=10)
            conn.execute(
                "INSERT INTO detection_logs (session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, now, obj_type, conf, img_path, temp, humi))
            conn.commit()
            conn.close()
        except Exception:
            pass

        try:
            conn = self.get_cloud_conn()
            conn.cursor().execute(
                "INSERT INTO detection_logs (session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (session_id, now, obj_type, conf, img_path, temp, humi))
            conn.close()
        except Exception:
            pass

    # ==========================================
    # 🔄 数据读取
    # ==========================================
    def fetch_sensor_logs(self, limit=50):
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            cursor = conn.cursor()
            # 更新查询语句，包含经纬度
            cursor.execute(
                'SELECT id, session_id, timestamp, distance, temperature, humidity, latitude, longitude, location_name, note FROM sensor_logs ORDER BY id DESC LIMIT ?',
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

    def update_detection_status(self, record_id, new_status):
        try:
            conn = sqlite3.connect(self.local_db_name, timeout=5)
            conn.execute("UPDATE detection_logs SET status = ? WHERE id = ?", (new_status, record_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ==========================================
    # 📡 断网容灾自动重传机制 (补全论文逻辑)
    # ==========================================
    def sync_offline_data(self):
        """同步断网期间遗留在本地的数据到云端"""
        print("🔄 正在检测并同步离线遗留数据到阿里云...")
        try:
            local_conn = sqlite3.connect(self.local_db_name, timeout=5)
            local_cursor = local_conn.cursor()

            cloud_conn = self.get_cloud_conn()
            cloud_cursor = cloud_conn.cursor()

            # 1. 补传丢失的巡逻会话 (patrol_sessions)
            local_cursor.execute("SELECT session_id, start_time, end_time, status FROM patrol_sessions")
            for row in local_cursor.fetchall():
                try:
                    # 使用 INSERT IGNORE，如果云端已经有了就不插入，没有的（断网期间的）就会被插入
                    cloud_cursor.execute(
                        "INSERT IGNORE INTO patrol_sessions (session_id, start_time, end_time, status) VALUES (%s, %s, %s, %s)",
                        row
                    )
                except Exception:
                    pass

            # 2. 补传丢失的检测记录 (detection_logs)
            local_cursor.execute(
                "SELECT id, session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi, status FROM detection_logs")
            for row in local_cursor.fetchall():
                try:
                    cloud_cursor.execute(
                        "INSERT IGNORE INTO detection_logs (id, session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        row
                    )
                except Exception:
                    pass

            # 3. 补传丢失的传感器记录 (sensor_logs)
            local_cursor.execute(
                "SELECT id, session_id, timestamp, distance, temperature, humidity, latitude, longitude, location_name, note FROM sensor_logs")
            for row in local_cursor.fetchall():
                try:
                    cloud_cursor.execute(
                        "INSERT IGNORE INTO sensor_logs (id, session_id, timestamp, distance, temperature, humidity, latitude, longitude, location_name, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        row
                    )
                except Exception:
                    pass

            cloud_conn.commit()
            cloud_conn.close()
            local_conn.close()
            print("✅ 离线数据同步完成！缺失数据已补齐至阿里云。")

        except Exception as e:
            print(f"⚠️ 同步失败 (可能网络仍未恢复): {e}")