import cv2
import platform

def detect_os():
    """
    识别操作系统
    """
    system = platform.system()
    if system == 'Linux':
        return 'Linux'
    elif system == 'Windows':
        return 'Windows'
    elif system == 'Darwin':
        return 'MacOS'
    
    return '未知系统'

def list_cameras(max_tested=10):
    # 根据操作系统选择适当的摄像头后端
    os_type = detect_os()
    backend = None
    if os_type == 'Windows':
        backend = cv2.CAP_DSHOW
    elif os_type == 'MacOS':
        backend = cv2.CAP_AVFOUNDATION
    # Linux不需要特殊指定后端，可以使用默认值
    
    available_cameras = []
    for i in range(max_tested):
        if backend is not None:
            cap = cv2.VideoCapture(i, backend)  # 使用特定后端打开摄像头
        else:
            cap = cv2.VideoCapture(i)  # Linux平台使用默认后端
        
        if cap.isOpened():  # 检查摄像头是否成功打开
            available_cameras.append(i)
            cap.release()  # 释放摄像头
        else:
            break  # 如果一个摄像头索引打不开，假设后面的都不可用
    return available_cameras

def capture_image(camera_index=0):
    # 根据操作系统选择适当的摄像头后端
    os_type = detect_os()
    backend = None
    if os_type == 'Windows':
        backend = cv2.CAP_DSHOW
    elif os_type == 'MacOS':
        backend = cv2.CAP_AVFOUNDATION
    # Linux不需要特殊指定后端，可以使用默认值
    
    # 使用适当的后端打开摄像头
    if backend is not None:
        cap = cv2.VideoCapture(camera_index, backend)
    else:
        cap = cv2.VideoCapture(camera_index)  # Linux平台使用默认后端
    
    if not cap.isOpened():
        print(f"Cannot open camera {camera_index}")
        return None

    ret, frame = cap.read()  # 读取一帧图像
    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        return None
    cap.release()  # 释放摄像头
    return frame

# 列出所有摄像头
cameras = list_cameras()
print("Available cameras:", cameras)

# 如果有可用摄像头，从第一个摄像头获取截图
if cameras:
    frame = capture_image(cameras[0])
    if frame is not None:
        cv2.imshow('Capture', frame)
        cv2.waitKey(0)  # 等待按键
        cv2.destroyAllWindows()
