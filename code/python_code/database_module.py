import sqlite3
import datetime
import os

class DatabaseManager:
    # 启用全新的 V2 数据库，避免和旧版本数据结构冲突
    def __init__(self, db_name="patrol_record_v2.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        # 开启外键支持
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # 1. 巡检任务会话表 (主表)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patrol_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT,
                end_time TEXT,
                status TEXT DEFAULT '巡逻中'
            )
        ''')

        # 2. 环境数据表 (子表)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT,
                distance REAL,
                temperature INTEGER,
                humidity INTEGER,
                note TEXT,
                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id)
            )
        ''')

        # 3. 巡检事件表 (子表 - 融合快照与状态机)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT,
                object_type TEXT,
                confidence REAL,
                image_path TEXT,
                snapshot_temp INTEGER,
                snapshot_humi INTEGER,
                status TEXT DEFAULT '🔴 待处理',
                FOREIGN KEY(session_id) REFERENCES patrol_sessions(session_id)
            )
        ''')

        conn.commit()
        conn.close()

    # === 任务批次生命周期 ===
    def start_session(self):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO patrol_sessions (start_time) VALUES (?)", (now,))
            session_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return session_id
        except Exception as e:
            print(f"Start Session DB Error: {e}")
            return None

    def end_session(self, session_id):
        if not session_id: return
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE patrol_sessions SET end_time = ?, status = '已结束' WHERE session_id = ?", (now, session_id))
            conn.commit()
            conn.close()
        except Exception as e: pass

    # === 数据插入 ===
    def insert_sensor_data(self, session_id, dist, temp, humi, note="定时记录"):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO sensor_logs (session_id, timestamp, distance, temperature, humidity, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, now, dist, temp, humi, note))
            conn.commit()
            conn.close()
        except Exception as e: pass

    def insert_detection_event(self, session_id, obj_type, conf, img_path, temp, humi):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO detection_logs (session_id, timestamp, object_type, confidence, image_path, snapshot_temp, snapshot_humi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, now, obj_type, conf, img_path, temp, humi))
            conn.commit()
            conn.close()
        except Exception as e: pass

    # === 状态机更新 ===
    def update_detection_status(self, record_id, new_status):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE detection_logs SET status = ? WHERE id = ?", (new_status, record_id))
            conn.commit()
            conn.close()
        except Exception as e: print(f"Update status error: {e}")

    # === 数据读取 ===
    def fetch_sensor_logs(self, limit=50):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            # 引入 session_id
            cursor.execute('SELECT id, session_id, timestamp, distance, temperature, humidity, note FROM sensor_logs ORDER BY id DESC LIMIT ?', (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except: return []

    def fetch_detection_logs(self, limit=50):
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            cursor = conn.cursor()
            # 提取所需字段，按需要展示
            cursor.execute('''
                SELECT id, session_id, status, timestamp, object_type, confidence, snapshot_temp, snapshot_humi, image_path 
                FROM detection_logs ORDER BY id DESC LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except: return []