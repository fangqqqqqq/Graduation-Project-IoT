import cv2
import threading
import time
import queue


class MyVideoCapture:
    def __init__(self, video_source):
        self.video_source = video_source
        # 增加 RTSP/HTTP 传输优化参数，降低延迟
        self.vid = cv2.VideoCapture(video_source, cv2.CAP_FFMPEG)
        self.q = queue.Queue(maxsize=1)
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while self.running:
            if self.vid.isOpened():
                ret, frame = self.vid.read()
                if not ret:
                    # 如果读取失败，尝试释放并重连
                    self.vid.release()
                    time.sleep(1)  # 等待一秒再试
                    # 尝试重新打开（简单的自动重连机制）
                    self.vid.open(self.video_source)
                    continue

                # 保持队列只有最新一帧
                if not self.q.empty():
                    try:
                        self.q.get_nowait()
                    except queue.Empty:
                        pass
                self.q.put((ret, frame))
            else:
                # 尝试打开
                self.vid.open(self.video_source)
                time.sleep(0.5)

    def get_frame(self):
        try:
            return self.q.get(timeout=0.1)
        except queue.Empty:
            return (False, None)

    def release(self):
        """显式释放资源"""
        self.running = False
        if self.vid and self.vid.isOpened():
            self.vid.release()

    def __del__(self):
        self.release()