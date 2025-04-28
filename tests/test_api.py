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
scene_change_queue = []  # 场景切换队列
camera_change_queue = []  # 机位切换队列

# 计数器，用于生成唯一ID
counter = 0

# 音频文件夹路径
audio_folders = ["./out/"]

# 场景列表
scene_list = ["客厅", "厨房", "卧室", "书房", "花园", "浴室", "阳台", "餐厅", "地下室", "车库"]

# 相机列表
camera_list = ["主机位", "特写机位", "俯视机位", "侧面机位", "远景机位", "近景机位", "后方机位", "跟踪机位", "环绕机位", "全景机位"]


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
                    "description": "打招呼动作组",
                    "actions": [
                        {
                            "name": "伸出右手朝向对方",
                            "match_words": [
                                "大家",
                                "你好",
                                "Hi",
                                "Hello",
                                "欢迎",
                                "来到直播间",
                                "早上好",
                                "下午好",
                                "晚上好",
                                "哈喽",
                                "大家好",
                                "各位好",
                                "各位观众",
                                "伙伴们",
                                "早安",
                                "午安",
                                "好久不见",
                                "NXZKQJYFPL",
                            ],
                            "priority": 10,
                        },
                        {
                            "name": "伸出双手朝向对方",
                            "match_words": [
                                "欢迎光临",
                                "非常欢迎",
                                "热烈欢迎",
                                "万分感谢",
                                "十分感谢",
                                "特别感谢",
                                "无比感谢",
                                "谢谢大家",
                                "谢谢各位",
                                "真诚感谢",
                                "BDJFKLQRST",
                            ],
                            "priority": 10,
                        },
                    ],
                },
                {
                    "id": 2,
                    "description": "表达观点动作组",
                    "actions": [
                        {
                            "name": "双手叉腰",
                            "match_words": [
                                "觉得",
                                "觉的",
                                "看来",
                                "你想",
                                "是不是",
                                "认为",
                                "感觉",
                                "依我看",
                                "据我",
                                "所知",
                                "就我看来",
                                "认为",
                                "DLEYCAFBEZ",
                            ],
                            "priority": 8,
                        }
                    ],
                },
                {
                    "id": 3,
                    "description": "思考动作组",
                    "actions": [
                        {
                            "name": "扶头思考",
                            "match_words": [
                                "我想想",
                                "额",
                                "这个",
                                "不确定",
                                "还在考虑",
                                "想一下",
                                "想想",
                                "我看看",
                                "理解",
                                "思考一下",
                                "想想",
                                "看看",
                                "查查",
                                "查询",
                                "YZLTXQBCSI",
                            ],
                            "priority": 6,
                        }
                    ],
                },
                {
                    "id": 4,
                    "description": "礼貌动作组",
                    "actions": [
                        {
                            "name": "荣幸地单手抱胸",
                            "match_words": [
                                "一定可",
                                "一定是",
                                "一定能",
                                "一定要",
                                "绝对可",
                                "绝对是",
                                "绝对能",
                                "绝对要",
                                "非常",
                                "满足",
                                "真心",
                                "太棒",
                                "荣幸",
                                "开心",
                                "有幸",
                                "深感荣幸",
                                "受宠若惊",
                                "激动",
                                "感谢",
                                "感激",
                                "GJHDQPLMVZ",
                            ],
                            "priority": 9,
                        }
                    ],
                },
                {
                    "id": 5,
                    "description": "鼓励动作组",
                    "actions": [
                        {
                            "name": "鼓掌",
                            "match_words": [
                                "加油",
                                "鼓励一下",
                                "不错",
                                "很棒",
                                "很好",
                                "干得好",
                                "精彩",
                                "厉害",
                                "给力",
                                "漂亮",
                                "赞",
                                "祝贺",
                                "欢呼",
                                "QPMVYETKHC",
                            ],
                            "priority": 8,
                        },
                        {
                            "name": "挥出双臂加油",
                            "match_words": [
                                "一起加油",
                                "加油吧",
                                "冲啊",
                                "我们能行",
                                "拼了",
                                "来吧",
                                "干吧",
                                "冲鸭",
                                "RDYJGKUZNT",
                            ],
                            "priority": 7,
                        },
                    ],
                },
                {
                    "id": 6,
                    "description": "否定动作组",
                    "actions": [
                        {
                            "name": "扣手扭捏",
                            "match_words": [
                                "不对",
                                "不是",
                                "不正确",
                                "不行",
                                "不太妥",
                                "有误",
                                "错了",
                                "不太对",
                                "不能",
                                "不用",
                                "不好",
                                "不妙",
                                "不可",
                                "不应",
                                "抱歉",
                                "FVLMXHQBZE",
                            ],
                            "priority": 2,
                        }
                    ],
                },
                {
                    "id": 7,
                    "description": "疑问动作组",
                    "actions": [
                        {
                            "name": "略带防御地抱胸并伸出右手",
                            "match_words": [
                                "why",
                                "what",
                                "how",
                                "什么",
                                "是什么",
                                "是哪个",
                                "为什么",
                                "怎么办",
                                "怎么做",
                                "怎么样",
                                "怎么搞",
                                "怎么用",
                                "怎么弄",
                                "如何",
                                "才是",
                                "为何",
                                "有没有",
                                "能否",
                                "怎样才",
                                "怎样能",
                                "如何能",
                                "如何才",
                                "请问",
                                "什么意思",
                                "解释",
                                "ZQXAHMWGJ",
                            ],
                            "priority": 1,
                        }
                    ],
                },
                {
                    "id": 8,
                    "description": "无语动作组",
                    "actions": [
                        {
                            "name": "扶头且很无语",
                            "match_words": [
                                "无语",
                                "不懂",
                                "我也是",
                                "我服了",
                                "呵呵",
                                "服了",
                                "哎呦",
                                "PLYBVCZTRN",
                            ],
                            "priority": 3,
                        }
                    ],
                },
                {
                    "id": 10,
                    "description": "拒绝动作组",
                    "actions": [
                        {
                            "name": "摆手拒绝",
                            "match_words": [
                                "不要",
                                "别",
                                "算了",
                                "不想",
                                "免了",
                                "别说了",
                                "算了吧",
                                "就这样吧",
                                "不用了",
                                "不必",
                                "TCBMZRHPQC",
                            ],
                            "priority": 6,
                        }
                    ],
                },
                {
                    "id": 11,
                    "description": "请求动作组",
                    "actions": [
                        {
                            "name": "双手合十拜托",
                            "match_words": [
                                "拜托",
                                "麻烦",
                                "请",
                                "能不能",
                                "求求你",
                                "劳烦",
                                "辛苦",
                                "拜托了",
                                "劳驾",
                                "麻烦各位",
                                "CDFYEPKHMI",
                            ],
                            "priority": 5,
                        }
                    ],
                },
            ]
        }


# 加载动作映射数据
action_mapping_data = load_action_mapping_data()


# 生成一条假的动作记录
def generate_fake_action_record():
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
            "audio_duration": get_audio_duration("./out/1.wav"),
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
        "欢迎大家来到我的直播间！",
    ]
    content = random.choice(contents)

    # 生成随机音频路径
    audio_extensions = [".wav"]
    audio_filenames = ["1", "2", "3", "4", "5"]
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
        "audio_duration": audio_duration,
    }

    print(f"生成假动作记录：{record}")

    return record


# 生成一条假的场景切换记录
def generate_fake_scene_record():
    global counter
    counter += 1

    # 随机选择一个场景
    scene_name = random.choice(scene_list)
    
    # 生成随机时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建场景记录
    record = {
        "id": counter,
        "name": scene_name,
        "type": "scene",
        "timestamp": timestamp,
        "formatted_time": timestamp,
        "is_executed": random.choice([True, False]),
    }
    
    print(f"生成假场景记录：{record}")
    
    return record


# 生成一条假的机位切换记录
def generate_fake_camera_record():
    global counter
    counter += 1

    # 随机选择一个机位
    camera_name = random.choice(camera_list)
    
    # 生成随机时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建机位记录
    record = {
        "id": counter,
        "name": camera_name,
        "type": "camera",
        "timestamp": timestamp,
        "formatted_time": timestamp,
        "is_executed": random.choice([True, False]),
    }
    
    print(f"生成假机位记录：{record}")
    
    return record


# 定时生成假数据的函数
def generate_fake_data_periodically():
    global action_mapping_queue, scene_change_queue, camera_change_queue
    while True:
        # 随机决定生成哪种记录
        record_type = random.choice(["action", "scene", "camera"])
        
        if record_type == "action":
            # 生成动作记录
            record = generate_fake_action_record()
            if record:
                action_mapping_queue.append(record)
                # 限制存储的记录数量，保持在最新的100条
                if len(action_mapping_queue) > 100:
                    action_mapping_queue = action_mapping_queue[-100:]
        
        elif record_type == "scene":
            # 生成场景记录
            record = generate_fake_scene_record()
            if record:
                scene_change_queue.append(record)
                # 限制存储的记录数量，保持在最新的50条
                if len(scene_change_queue) > 50:
                    scene_change_queue = scene_change_queue[-50:]
        
        elif record_type == "camera":
            # 生成机位记录
            record = generate_fake_camera_record()
            if record:
                camera_change_queue.append(record)
                # 限制存储的记录数量，保持在最新的50条
                if len(camera_change_queue) > 50:
                    camera_change_queue = camera_change_queue[-50:]

        # 随机等待3-8秒
        time.sleep(random.randint(3, 8))


# 通用响应模型
class CommonResult:
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data if data is not None else {}

    def dict(self):
        return {"code": self.code, "message": self.message, "data": self.data}


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

        return CommonResult(
            code=200, data=result_data, message="获取动作映射记录成功！"
        ).dict()
    except Exception as e:
        print(f"获取动作映射记录失败！{e}")
        return CommonResult(
            code=-1, message=f"获取动作映射记录失败！{e}", data={}
        ).dict()


# API路由定义 - 删除动作映射记录
@app.post("/delete_action_mapping")
async def delete_action_mapping(
    action_id: Optional[int] = None, delete_all: Optional[bool] = False
):
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
            action_mapping_queue = [
                record for record in action_mapping_queue if record["id"] != action_id
            ]

            if len(action_mapping_queue) < original_length:
                return CommonResult(
                    code=200, message=f"删除动作映射记录 {action_id} 成功！"
                ).dict()
            else:
                return CommonResult(
                    code=400,
                    message=f"删除动作映射记录失败，没有找到ID为 {action_id} 的记录！",
                ).dict()

        return CommonResult(
            code=400, message="删除动作映射记录失败，未指定action_id或delete_all参数！"
        ).dict()
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
            if filename.endswith((".wav", ".mp3", ".ogg")):
                file_path = os.path.join("./out", filename)
                duration = get_audio_duration(file_path)
                audio_files.append(
                    {
                        "filename": filename,
                        "url": f"/out/{filename}",
                        "full_path": file_path,
                        "duration": duration,
                    }
                )

        return CommonResult(
            code=200,
            message="获取音频文件列表成功",
            data={"files": audio_files, "count": len(audio_files)},
        ).dict()
    except Exception as e:
        print(f"获取音频文件列表失败：{e}")
        return CommonResult(code=-1, message=f"获取音频文件列表失败：{e}").dict()


# API路由定义 - 添加场景切换记录
@app.post("/add_scene_change")
async def add_scene_change(scene_name: str):
    """
    添加场景切换记录
    
    参数:
        scene_name: 场景名称
    """
    try:
        # 创建新记录
        global counter
        counter += 1
        
        record = {
            "id": counter,
            "name": scene_name,
            "type": "scene",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_executed": False
        }
        
        scene_change_queue.append(record)
        
        return CommonResult(code=200, message="添加场景切换记录成功！").dict()
    except Exception as e:
        print(f"添加场景切换记录失败！{e}")
        return CommonResult(code=-1, message=f"添加场景切换记录失败！{e}").dict()


# API路由定义 - 添加机位切换记录
@app.post("/add_camera_change")
async def add_camera_change(camera_name: str):
    """
    添加机位切换记录
    
    参数:
        camera_name: 机位名称
    """
    try:
        # 创建新记录
        global counter
        counter += 1
        
        record = {
            "id": counter,
            "name": camera_name,
            "type": "camera",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "formatted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_executed": False
        }
        
        camera_change_queue.append(record)
        
        return CommonResult(code=200, message="添加机位切换记录成功！").dict()
    except Exception as e:
        print(f"添加机位切换记录失败！{e}")
        return CommonResult(code=-1, message=f"添加机位切换记录失败！{e}").dict()


# API路由定义 - 获取场景/机位切换记录
@app.get("/get_scene_camera_changes")
async def get_scene_camera_changes(change_type: Optional[str] = None, limit: Optional[int] = None):
    """
    获取场景/机位切换记录
    
    参数:
        change_type: 变更类型，可选 'scene'(场景)、'camera'(机位)或None(全部)
        limit: 返回的记录数量限制，None表示返回全部
    """
    try:
        # 根据类型筛选数据
        if change_type == "scene":
            data = scene_change_queue
        elif change_type == "camera":
            data = camera_change_queue
        else:
            # 合并两种类型的数据
            data = scene_change_queue + camera_change_queue
            # 按时间倒序排序
            data.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # 限制返回数量
        if limit is not None and limit > 0:
            data = data[-limit:]
        
        result_data = {"data": data, "count": len(data), "queue_count": len(data)}
        
        return CommonResult(
            code=200, data=result_data, message="获取场景/机位切换记录成功！"
        ).dict()
    except Exception as e:
        print(f"获取场景/机位切换记录失败！{e}")
        return CommonResult(
            code=-1, message=f"获取场景/机位切换记录失败！{e}", data={}
        ).dict()


# API路由定义 - 删除场景/机位切换记录
@app.post("/delete_scene_camera_change")
async def delete_scene_camera_change(
    change_id: Optional[int] = None, 
    change_type: Optional[str] = None, 
    delete_all: Optional[bool] = False
):
    """
    删除场景/机位切换记录
    
    参数:
        change_id: 要删除的记录ID，None表示不按ID删除
        change_type: 变更类型，可选 'scene'(场景)、'camera'(机位)或None(全部)
        delete_all: 是否删除所有记录
    """
    global scene_change_queue, camera_change_queue
    
    try:
        success = False
        
        if delete_all:
            # 根据类型删除全部记录
            if change_type == "scene" or change_type is None:
                scene_change_queue = []
                success = True
            
            if change_type == "camera" or change_type is None:
                camera_change_queue = []
                success = True
                
            if success:
                return CommonResult(code=200, message="删除所有场景/机位切换记录成功！").dict()
        
        elif change_id is not None:
            # 根据ID删除记录
            if change_type == "scene" or change_type is None:
                original_length = len(scene_change_queue)
                scene_change_queue = [
                    record for record in scene_change_queue if record["id"] != change_id
                ]
                if len(scene_change_queue) < original_length:
                    success = True
            
            if change_type == "camera" or change_type is None and not success:
                original_length = len(camera_change_queue)
                camera_change_queue = [
                    record for record in camera_change_queue if record["id"] != change_id
                ]
                if len(camera_change_queue) < original_length:
                    success = True
            
            if success:
                return CommonResult(
                    code=200, message=f"删除场景/机位切换记录 {change_id} 成功！"
                ).dict()
            else:
                return CommonResult(
                    code=400,
                    message=f"删除场景/机位切换记录失败，没有找到ID为 {change_id} 的记录！",
                ).dict()
        
        return CommonResult(
            code=400, message="删除场景/机位切换记录失败，未指定change_id或delete_all参数！"
        ).dict()
    except Exception as e:
        print(f"删除场景/机位切换记录失败！{e}")
        return CommonResult(code=-1, message=f"删除场景/机位切换记录失败！{e}").dict()


# API路由定义 - 添加动作映射记录
@app.post("/add_action_mapping")
async def add_action_mapping(action_name: str, action_id: int):
    """
    添加动作映射记录
    
    参数:
        action_name: 动作名称
        action_id: 动作ID
    """
    try:
        # 查找action_id对应的组信息
        group_desc = "默认分组"
        for group in action_mapping_data.get("groups", []):
            if group.get("id") == action_id:
                group_desc = group.get("description", "未知分组")
                break
        
        # 创建新记录
        global counter
        counter += 1
        
        record = {
            "id": counter,
            "action_name": action_name,
            "match_word": "手动添加",
            "priority": random.randint(1, 10),
            "group_id": action_id,
            "group_description": group_desc,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_executed": False,
            "content": "这是一条手动添加的动作记录",
            "audio_path": "./out/1.wav",
            "audio_url": "http://127.0.0.1:8000/out/1.wav",
            "audio_duration": get_audio_duration("./out/1.wav"),
        }
        
        action_mapping_queue.append(record)
        
        return CommonResult(code=200, message="添加动作映射记录成功！").dict()
    except Exception as e:
        print(f"添加动作映射记录失败！{e}")
        return CommonResult(code=-1, message=f"添加动作映射记录失败！{e}").dict()


# 启动定时生成假数据的线程
threading.Thread(target=generate_fake_data_periodically, daemon=True).start()

if __name__ == "__main__":
    # 启动FastAPI应用
    # 可以添加host参数以便于在局域网中访问
    uvicorn.run(app, host="0.0.0.0", port=8000)
