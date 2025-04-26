from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 导入StaticFiles用于挂载静态目录
import uvicorn
import json
import random
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

# 创建FastAPI应用
app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
# 确保out目录存在
os.makedirs("./out", exist_ok=True)
# 将out目录挂载为/audio路径
app.mount("/out", StaticFiles(directory="./out"), name="out")

# 全局变量，用于存储生成的假数据
action_mapping_queue = []

# 计数器，用于生成唯一ID
counter = 0

# 音频文件夹路径
audio_folders = ["./out/"]

# 使用假的音频时长计算函数替代 AudioSegment
def get_audio_duration(audio_path):
    # 仅返回随机时长，不再依赖 AudioSegment
    return round(random.uniform(2.0, 15.0), 2)

# 从config.json文件中加载动作映射数据
def load_action_mapping_data():
    try:
        with open("config.json", "r", encoding="utf-8") as file:
            config_data = json.load(file)
            return config_data.get("action_mapping", {})
    except Exception as e:
        print(f"加载config.json文件失败: {e}")
        # 返回假数据，确保功能正常运行
        return {
            "groups": [
                {
                    "id": 1,
                    "description": "默认分组",
                    "actions": [
                        {
                            "name": "微笑",
                            "match_words": ["开心", "高兴", "微笑"],
                            "priority": 1
                        },
                        {
                            "name": "招手",
                            "match_words": ["你好", "欢迎", "招手"],
                            "priority": 2
                        }
                    ]
                }
            ]
        }

# 加载动作映射数据
action_mapping_data = load_action_mapping_data()

# 生成一条假的动作记录
def generate_fake_action_record():
    print("生成假的动作记录")
    global counter
    counter += 1
    
    # 随机选择一个动作组
    if not action_mapping_data or "groups" not in action_mapping_data:
        # 如果无法读取配置，生成一个默认动作
        record = {
            "id": counter,
            "action_name": "默认动作",
            "match_word": "默认关键词",
            "priority": 0,
            "group_id": 0,
            "group_description": "默认分组",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_executed": random.choice([True, False]),
            "content": "这是一条默认生成的消息内容",
            "audio_path": "./out/1.wav",
            "audio_url": "http://127.0.0.1:8000/out/1.wav",
            "audio_duration": get_audio_duration("./out/1.wav")
        }
        return record
    
    group = random.choice(action_mapping_data.get("groups", []))
    if not group or "actions" not in group:
        return None
    
    # 随机选择一个动作
    action = random.choice(group.get("actions", []))
    if not action:
        return None
    
    # 随机选择一个匹配词
    match_word = random.choice(action.get("match_words", ["未知关键词"]))
    
    # 生成随机时间戳（最近24小时内）
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 生成随机内容文本
    contents = [
        "你好，今天天气真不错！",
        "我们要好好学习，天天向上。",
        "人工智能的发展真是日新月异。",
        "这个问题我需要认真思考一下。",
        "欢迎大家来到我的直播间！"
    ]
    content = random.choice(contents)
    
    # 生成随机音频路径
    audio_extensions = [".wav"]
    audio_filenames = [
        "1", "2", "3", "4", "5"
    ]
    audio_filename = random.choice(audio_filenames) + random.choice(audio_extensions)
    audio_path = os.path.join("./out", audio_filename)
    
    # 生成音频URL - 现在直接使用挂载的静态目录
    audio_url = f"/out/{audio_filename}"
    
    # 获取音频时长
    audio_duration = get_audio_duration(audio_path)
    
    # 构建动作记录
    record = {
        "id": counter,
        "action_name": action.get("name", "未知动作"),
        "match_word": match_word,
        "priority": action.get("priority", 0),
        "group_id": group.get("id", 0),
        "group_description": group.get("description", "未知分组"),
        "timestamp": timestamp,
        "is_executed": random.choice([True, False]),
        "content": content,
        "audio_path": audio_path,
        "audio_url": f"http://127.0.0.1:8000{audio_url}",
        "audio_duration": audio_duration
    }
    
    return record

# 定时生成假数据的函数
def generate_fake_data_periodically():
    global action_mapping_queue
    while True:
        # 生成动作记录
        record = generate_fake_action_record()
        if record:
            action_mapping_queue.append(record)
            # 限制存储的记录数量，保持在最新的100条
            if len(action_mapping_queue) > 100:
                action_mapping_queue = action_mapping_queue[-100:]
        
        # 随机等待3-8秒
        time.sleep(random.randint(3, 8))

# 通用响应模型
class CommonResult:
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data if data is not None else {}
        
    def dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data
        }

# API路由定义 - 获取动作映射记录
@app.get("/get_action_mapping")
async def get_action_mapping(limit: Optional[int] = None):
    """
    获取动作映射记录
    
    参数:
        limit: 返回的记录数量限制，None表示返回全部
    """
    try:
        data = action_mapping_queue
        
        if limit is not None and limit > 0:
            data = data[-limit:]
        
        result_data = {"data": data, "count": len(data)}
        
        return CommonResult(code=200, data=result_data, message="获取动作映射记录成功！").dict()
    except Exception as e:
        print(f"获取动作映射记录失败！{e}")
        return CommonResult(code=-1, message=f"获取动作映射记录失败！{e}", data={}).dict()

# API路由定义 - 删除动作映射记录
@app.post("/delete_action_mapping")
async def delete_action_mapping(action_id: Optional[int] = None, delete_all: Optional[bool] = False):
    """
    删除动作映射记录
    
    参数:
        action_id: 要删除的动作ID，None表示不按ID删除
        delete_all: 是否删除所有记录
    """
    global action_mapping_queue
    
    try:
        if delete_all:
            action_mapping_queue = []
            return CommonResult(code=200, message="删除所有动作映射记录成功！").dict()
        
        if action_id is not None:
            original_length = len(action_mapping_queue)
            action_mapping_queue = [record for record in action_mapping_queue if record["id"] != action_id]
            
            if len(action_mapping_queue) < original_length:
                return CommonResult(code=200, message=f"删除动作映射记录 {action_id} 成功！").dict()
            else:
                return CommonResult(code=400, message=f"删除动作映射记录失败，没有找到ID为 {action_id} 的记录！").dict()
        
        return CommonResult(code=400, message="删除动作映射记录失败，未指定action_id或delete_all参数！").dict()
    except Exception as e:
        print(f"删除动作映射记录失败！{e}")
        return CommonResult(code=-1, message=f"删除动作映射记录失败！{e}").dict()

# API路由定义 - 获取可用的音频文件列表
@app.get("/list_audio_files")
async def list_audio_files():
    """
    获取out目录中可用的音频文件列表
    """
    try:
        audio_files = []
        for filename in os.listdir("./out"):
            if filename.endswith(('.wav', '.mp3', '.ogg')):
                file_path = os.path.join("./out", filename)
                duration = get_audio_duration(file_path)
                audio_files.append({
                    "filename": filename,
                    "url": f"/out/{filename}",
                    "full_path": file_path,
                    "duration": duration
                })
        
        return CommonResult(
            code=200, 
            message="获取音频文件列表成功", 
            data={"files": audio_files, "count": len(audio_files)}
        ).dict()
    except Exception as e:
        print(f"获取音频文件列表失败：{e}")
        return CommonResult(code=-1, message=f"获取音频文件列表失败：{e}").dict()

# 启动定时生成假数据的线程
threading.Thread(target=generate_fake_data_periodically, daemon=True).start()

if __name__ == "__main__":
    # 启动FastAPI应用
    # 可以添加host参数以便于在局域网中访问
    uvicorn.run(app, host="0.0.0.0", port=8000) 