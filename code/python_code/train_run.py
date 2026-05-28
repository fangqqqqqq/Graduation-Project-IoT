from ultralytics import YOLO

if __name__ == '__main__':
    # 1. 加载模型
    # 必须用 n (nano) 版本，因为它是参数最少、计算量最小的
    print("正在加载 YOLOv8n 模型 (CPU模式)...")
    model = YOLO('yolov8n-cbam.yaml')

    # 2. 开始训练
    print("🚀 开始 CPU 训练 (这需要很长时间，请耐心等待)...")

    model.train(
        # 数据集路径
        data=r"D:\Graduation_Project\My First Project.v1-v1.yolov8\data.yaml",

        # 图片大小
        imgsz=640,

        # 🟢 修改1：轮数建议先减少
        # CPU 跑 150 轮可能需要几天时间。
        # 建议先跑 50 轮看看效果，或者做好通宵挂机的准备。
        epochs=50,

        # 🟢 修改2：批次大小 (Batch Size) 必须改小
        # CPU 一次处理不了太多图片。设为 4 或 8 是比较安全的。
        # 如果电脑内存小于 8G，建议设为 2；如果 16G 内存，设为 4 或 8。
        batch=4,

        # 🟢 修改3：强制使用 CPU
        device='cpu',

        # 线程数 (Windows 下保持 0)
        workers=0,

        # 早停机制
        patience=10,

        # 结果保存的名字
        name='city_patrol_cbam_run'
    )