import os, sys, threading, json, random
import difflib
from datetime import datetime
import traceback
import importlib
import asyncio

import copy
import re
from functools import partial


from .config import Config
from .common import Common
from .audio import Audio
from .my_log import logger
from .db import SQLiteDB


"""
	___ _                       
	|_ _| | ____ _ _ __ ___  ___ 
	 | || |/ / _` | '__/ _ \/ __|
	 | ||   < (_| | | | (_) \__ \
	|___|_|\_\__,_|_|  \___/|___/

"""
class SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
            return cls._instances[cls]


class My_handle(metaclass=SingletonMeta):
    common = None
    config = None
    audio = None
    my_translate = None
    
    # 是否在数据处理中
    is_handleing = 0

    # 异常报警数据
    abnormal_alarm_data = {
        "platform": {
            "error_count": 0
        },
        "llm": {
            "error_count": 0
        },
        "tts": {
            "error_count": 0
        },
        "svc": {
            "error_count": 0
        },
        "visual_body": {
            "error_count": 0
        },
        "other": {
            "error_count": 0
        }
    }

    # 直播消息存储(入场、礼物、弹幕)，用于限定时间内的去重
    live_data = {
        "comment": [],
        "gift": [],
        "entrance": [],
    }

    # 各个任务运行数据缓存 暂时用于 限定任务周期性触发
    task_data = {
        "read_comment": {
            "data": [],
            "time": 0
        },
        "local_qa": {
            "data": [],
            "time": 0
        },
        "thanks": {
            "gift": {
                "data": [],
                "time": 0
            },
            "entrance": {
                "data": [],
                "time": 0
            },
            "follow": {
                "data": [],
                "time": 0
            },
        }
    }

    # 答谢板块文案数据临时存储
    thanks_entrance_copy = []
    thanks_gift_copy = []
    thanks_follow_copy = []

    def __init__(self, config_path):
        logger.info("初始化My_handle...")

        try:
            if My_handle.common is None:
                My_handle.common = Common()
            if My_handle.config is None:
                My_handle.config = Config(config_path)
            if My_handle.audio is None:
                My_handle.audio = Audio(config_path)

            self.proxy = None
            # self.proxy = {
            #     "http": "http://127.0.0.1:10809",
            #     "https": "http://127.0.0.1:10809"
            # }
            
            # 数据丢弃部分相关的实现
            self.data_lock = threading.Lock()
            self.timers = {}

            self.db = None

            # 设置会话初始值
            self.session_config = None
            self.sessions = {}
            self.current_key_index = 0

            # 点歌模块
            self.choose_song_song_lists = None

           

            # 配置加载
            self.config_load()

            logger.info(f"配置数据加载成功。")

            # 启动定时器
            self.start_timers()
        except Exception as e:
            logger.error(traceback.format_exc())     

    # 清空 待合成消息队列|待播放音频队列
    def clear_queue(self, type: str="message_queue"):
        """清空 待合成消息队列|待播放音频队列

        Args:
            type (str, optional): 队列类型. Defaults to "message_queue".

        Returns:
            bool: 清空结果
        """
        try:
            return My_handle.audio.clear_queue(type)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"清空{type}队列失败：{e}")
            return False
        
    # 停止音频播放
    def stop_audio(self, type: str="pygame", mixer_normal: bool=True, mixer_copywriting: bool=True):
        try:
            return My_handle.audio.stop_audio(type, mixer_normal, mixer_copywriting)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"停止音频播放失败：{e}")
            return False

    # 周期性触发数据处理，每秒执行一次，进行计时
    def periodic_trigger_data_handle(self):
        def get_last_n_items(data_list: list, num: int):
            # 返回最后的 n 个元素，如果不足 n 个则返回实际元素个数
            return data_list[-num:] if num > 0 else []
        
        
        if My_handle.config.get("read_comment", "periodic_trigger", "enable"):
            type = "read_comment"
            # 计时+1
            My_handle.task_data[type]["time"] += 1
            
            periodic_time_min = int(My_handle.config.get(type, "periodic_trigger", "periodic_time_min"))
            periodic_time_max = int(My_handle.config.get(type, "periodic_trigger", "periodic_time_max"))
            # 生成触发周期值
            periodic_time = random.randint(periodic_time_min, periodic_time_max)
            logger.debug(f"type={type}, periodic_time={periodic_time}, My_handle.task_data={My_handle.task_data}")

            # 计时时间是否超过限定的触发周期
            if My_handle.task_data[type]["time"] >= periodic_time:
                # 计时清零
                My_handle.task_data[type]["time"] = 0

                trigger_num_min = int(My_handle.config.get(type, "periodic_trigger", "trigger_num_min"))
                trigger_num_max = int(My_handle.config.get(type, "periodic_trigger", "trigger_num_max"))
                # 生成触发个数
                trigger_num = random.randint(trigger_num_min, trigger_num_max)
                # 获取数据
                data_list = get_last_n_items(My_handle.task_data[type]["data"], trigger_num)
                logger.debug(f"type={type}, trigger_num={trigger_num}")

                if data_list != []:
                    # 遍历数据 进行webui数据回传 和 音频合成播放
                    for data in data_list:
                        self.audio_synthesis_handle(data)

                # 数据清空
                My_handle.task_data[type]["data"] = []
        

        
        if My_handle.config.get("thanks", "gift", "periodic_trigger", "enable"):
            type = "thanks"
            type2 = "gift"

            # 计时+1
            My_handle.task_data[type][type2]["time"] += 1

            periodic_time_min = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_min"))
            periodic_time_max = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_max"))
            # 生成触发周期值
            periodic_time = random.randint(periodic_time_min, periodic_time_max)
            logger.debug(f"type={type}, periodic_time={periodic_time}, My_handle.task_data={My_handle.task_data}")

            # 计时时间是否超过限定的触发周期
            if My_handle.task_data[type][type2]["time"] >= periodic_time:
                # 计时清零
                My_handle.task_data[type][type2]["time"] = 0

                trigger_num_min = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_min"))
                trigger_num_max = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_max"))
                # 生成触发个数
                trigger_num = random.randint(trigger_num_min, trigger_num_max)
                # 获取数据
                data_list = get_last_n_items(My_handle.task_data[type][type2]["data"], trigger_num)
                logger.debug(f"type={type}, trigger_num={trigger_num}")

                if data_list != []:
                    # 遍历数据 进行webui数据回传 和 音频合成播放
                    for data in data_list:
                        self.audio_synthesis_handle(data)

                # 数据清空
                My_handle.task_data[type][type2]["data"] = []
        
        if My_handle.config.get("thanks", "entrance", "periodic_trigger", "enable"):
            type = "thanks"
            type2 = "entrance"

            # 计时+1
            My_handle.task_data[type][type2]["time"] += 1

            periodic_time_min = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_min"))
            periodic_time_max = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_max"))
            # 生成触发周期值
            periodic_time = random.randint(periodic_time_min, periodic_time_max)
            logger.debug(f"type={type}, periodic_time={periodic_time}, My_handle.task_data={My_handle.task_data}")

            # 计时时间是否超过限定的触发周期
            if My_handle.task_data[type][type2]["time"] >= periodic_time:
                # 计时清零
                My_handle.task_data[type][type2]["time"] = 0

                trigger_num_min = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_min"))
                trigger_num_max = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_max"))
                # 生成触发个数
                trigger_num = random.randint(trigger_num_min, trigger_num_max)
                # 获取数据
                data_list = get_last_n_items(My_handle.task_data[type][type2]["data"], trigger_num)
                logger.debug(f"type={type}, trigger_num={trigger_num}")

                if data_list != []:
                    # 遍历数据 进行webui数据回传 和 音频合成播放
                    for data in data_list:
                        self.audio_synthesis_handle(data)

                # 数据清空
                My_handle.task_data[type][type2]["data"] = []

        if My_handle.config.get("thanks", "follow", "periodic_trigger", "enable"):
            type = "thanks"
            type2 = "follow"

            # 计时+1
            My_handle.task_data[type][type2]["time"] += 1

            periodic_time_min = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_min"))
            periodic_time_max = int(My_handle.config.get(type, type2, "periodic_trigger", "periodic_time_max"))
            # 生成触发周期值
            periodic_time = random.randint(periodic_time_min, periodic_time_max)
            logger.debug(f"type={type}, periodic_time={periodic_time}, My_handle.task_data={My_handle.task_data}")

            # 计时时间是否超过限定的触发周期
            if My_handle.task_data[type][type2]["time"] >= periodic_time:
                # 计时清零
                My_handle.task_data[type][type2]["time"] = 0

                trigger_num_min = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_min"))
                trigger_num_max = int(My_handle.config.get(type, type2, "periodic_trigger", "trigger_num_max"))
                # 生成触发个数
                trigger_num = random.randint(trigger_num_min, trigger_num_max)
                # 获取数据
                data_list = get_last_n_items(My_handle.task_data[type][type2]["data"], trigger_num)
                logger.debug(f"type={type}, trigger_num={trigger_num}")

                if data_list != []:
                    # 遍历数据 进行webui数据回传 和 音频合成播放
                    for data in data_list:
                        self.audio_synthesis_handle(data)

                # 数据清空
                My_handle.task_data[type][type2]["data"] = []


        self.periodic_trigger_timer = threading.Timer(1, partial(self.periodic_trigger_data_handle))
        self.periodic_trigger_timer.start()

    # 清空live_data直播数据
    def clear_live_data(self, type: str=""):
        if type != "" and type is not None:
            My_handle.live_data[type] = []

        if type == "comment":
            self.comment_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "comment")), partial(self.clear_live_data, "comment"))
            self.comment_check_timer.start()
        elif type == "gift":
            self.gift_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "gift")), partial(self.clear_live_data, "gift"))
            self.gift_check_timer.start()
        elif type == "entrance":
            self.entrance_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "entrance")), partial(self.clear_live_data, "entrance"))
            self.entrance_check_timer.start()

    # 启动定时器
    def start_timers(self):
        
        if My_handle.config.get("filter", "limited_time_deduplication", "enable"):

            # 设置定时器，每隔n秒执行一次
            self.comment_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "comment")), partial(self.clear_live_data, "comment"))
            self.comment_check_timer.start()

            self.gift_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "gift")), partial(self.clear_live_data, "gift"))
            self.gift_check_timer.start()

            self.entrance_check_timer = threading.Timer(int(My_handle.config.get("filter", "limited_time_deduplication", "entrance")), partial(self.clear_live_data, "entrance"))
            self.entrance_check_timer.start()

            logger.info("启动 限定时间直播数据去重 定时器")

        self.periodic_trigger_timer = threading.Timer(1, partial(self.periodic_trigger_data_handle))
        self.periodic_trigger_timer.start()
        logger.info("启动 周期性触发 定时器")


    # 是否位于数据处理状态
    def is_handle_empty(self):
        return My_handle.is_handleing


    # 音频队列、播放相关情况
    def is_audio_queue_empty(self):
        return My_handle.audio.is_audio_queue_empty()

    # 判断 等待合成消息队列|待播放音频队列 数是否小于或大于某个值，就返回True
    def is_queue_less_or_greater_than(self, type: str="message_queue", less: int=None, greater: int=None):
        """判断 等待合成消息队列|待播放音频队列 数是否小于或大于某个值

        Args:
            type (str, optional): _description_. Defaults to "message_queue" | voice_tmp_path_queue.
            less (int, optional): _description_. Defaults to None.
            greater (int, optional): _description_. Defaults to None.

        Returns:
            bool: 是否小于或大于某个值
        """
        return My_handle.audio.is_queue_less_or_greater_than(type, less, greater)

    # 获取音频类信息
    def get_audio_info(self):
        return My_handle.audio.get_audio_info()

    def handle_chat_type(self):
        chat_type = My_handle.config.get("chat_type")

        if chat_type == "chatterbot":
            from chatterbot import ChatBot
            self.chatterbot_config = My_handle.config.get("chatterbot")
            try:
                self.bot = ChatBot(
                    self.chatterbot_config["name"],
                    database_uri='sqlite:///' + self.chatterbot_config["db_path"]
                )
            except Exception as e:
                logger.info(e)
                exit(0)

    # 配置加载
    def config_load(self):
        self.session_config = {'msg': [{"role": "system", "content": My_handle.config.get('chatgpt', 'preset')}]}

        # 聊天相关类实例化
        self.handle_chat_type()

        # 日志文件路径
        self.log_file_path = "./log/log-" + My_handle.common.get_bj_time(1) + ".txt"
        if os.path.isfile(self.log_file_path):
            logger.info(f'{self.log_file_path} 日志文件已存在，跳过')
        else:
            with open(self.log_file_path, 'w') as f:
                f.write('')
                logger.info(f'{self.log_file_path} 日志文件已创建')

        # 生成弹幕文件
        self.comment_file_path = "./log/comment-" + My_handle.common.get_bj_time(1) + ".txt"
        if os.path.isfile(self.comment_file_path):
            logger.info(f'{self.comment_file_path} 弹幕文件已存在，跳过')
        else:
            with open(self.comment_file_path, 'w') as f:
                f.write('')
                logger.info(f'{self.comment_file_path} 弹幕文件已创建')

        """                                                                                                                
                                                                                                                                        
            .............  '>)xcn)I                                                                                 
            }}}}}}}}}}}}](v0kaaakad\..                                                                              
            ++++++~~++<_xpahhhZ0phah>                                                                               
            _________+(OhhkamuCbkkkh+                                                                               
            ?????????nbhkhkn|makkkhQ^                                                                               
            [[[[[[[}UhkbhZ]fbhkkkhb<                                                                                
            1{1{1{1ChkkaXicohkkkhk]                                                                                 
            ))))))JhkkhrICakkkkap-                                                                                  
            \\\\|ckkkat;0akkkka0>                                                                                   
            ttt/fpkka/;Oakhhaku"                                                                                    
            jjjjUmkau^QabwQX\< '!<++~>iI       .;>++++<>I'     :+}}{?;                                              
            xxxcpdkO"capmmZ/^ +Y-;,,;-Lf     ItX/+l:",;>1cx>  .`"x#d>`        .`.                                   
            uuvqwkh+1ahaaL_  'Zq;     ;~   '/bQ!         "uhc: . 1oZ'         "vj.     ^'                           
            ccc0kaz!kawX}'   .\hbv?:      .jop;           .C*L^  )oO`        .':I^. ."_L!^^.    ':;,'               
            XXXXph_cU_"        >rZhbC\!   "qaC...          faa~  )oO`        ;-jqj .l[mb1]_'  ^(|}\Ow{              
            XXXz00i+             '!1Ukkc, 'JoZ` .          uop;  )oO'          >ou   .Lp"  . ,0j^^>Yvi              
            XXXzLn. .        ^>      lC#(  lLot.          _kq- . 1o0'          >on   .Qp,    }*|><i^  .             
            YYYXQ|           ,O]^.   "XQI . `10c~^.    '!t0f:   .t*q;....'l1. ._#c.. .Qkl`I_"Iw0~"`,<|i.            
            (|((f1           ^t1]++-}(?`      '>}}}/rrx1]~^    ^?jvv/]--]{r) .i{x/+;  ]Xr1_;. :(vnrj\i.             
                '1..             .''.   .         .Itq*Z}`             ..                                           
                 +; .                                "}XmQf-i!;.                                                    
                  .                                     ';><iI"                                                     
                                                                                                                                        
                                                                                                                                                                                                                                                     
        """
        try:
            # 数据库
            self.db = SQLiteDB(My_handle.config.get("database", "path"))
            logger.info(f'创建数据库:{My_handle.config.get("database", "path")}')

            # 创建弹幕表
            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS danmu (
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                ts DATETIME NOT NULL
            )
            '''
            self.db.execute(create_table_sql)
            logger.debug('创建danmu（弹幕）表')

            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS entrance (
                username TEXT NOT NULL,
                ts DATETIME NOT NULL
            )
            '''
            self.db.execute(create_table_sql)
            logger.debug('创建entrance（入场）表')

            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS gift (
                username TEXT NOT NULL,
                gift_name TEXT NOT NULL,
                gift_num INT NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                ts DATETIME NOT NULL
            )
            '''
            self.db.execute(create_table_sql)
            logger.debug('创建gift（礼物）表')

            create_table_sql = '''
            CREATE TABLE IF NOT EXISTS integral (
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                uid TEXT NOT NULL,
                integral INT NOT NULL,
                view_num INT NOT NULL,
                sign_num INT NOT NULL,
                last_sign_ts DATETIME NOT NULL,
                total_price INT NOT NULL,
                last_ts DATETIME NOT NULL
            )
            '''
            self.db.execute(create_table_sql)
            logger.debug('创建integral（积分）表')
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'数据库 {My_handle.config.get("database", "path")} 创建失败，请查看日志排查问题！！！')


    # 重载config
    def reload_config(self, config_path):
        My_handle.config = Config(config_path)
        My_handle.audio.reload_config(config_path)
        My_handle.my_translate.reload_config(config_path)

        self.config_load()


    # 回传给webui，用于聊天内容显示
    def webui_show_chat_log_callback(self, data_type: str, data: dict, resp_content: str):
        """回传给webui，用于聊天内容显示

        Args:
            data_type (str): 数据内容的类型（多指LLM）
            data (dict): 数据JSON
            resp_content (str): 显示的聊天内容的文本
        """
        try:
            if My_handle.config.get("talk", "show_chat_log") == True: 
                if "ori_username" not in data:
                    data["ori_username"] = data["username"]
                if "ori_content" not in data:
                    data["ori_content"] = data["content"]
                    
                # 返回给webui的数据
                return_webui_json = {
                    "type": "llm",
                    "data": {
                        "type": data_type,
                        "username": data["ori_username"], 
                        "content_type": "answer",
                        "content": f"错误：{data_type}无返回，请查看日志" if resp_content is None else resp_content,
                        "timestamp": My_handle.common.get_bj_time(0)
                    }
                }

                webui_ip = "127.0.0.1" if My_handle.config.get("webui", "ip") == "0.0.0.0" else My_handle.config.get("webui", "ip")
                tmp_json = My_handle.common.send_request(f'http://{webui_ip}:{My_handle.config.get("webui", "port")}/callback', "POST", return_webui_json, timeout=30)
        except Exception as e:
            logger.error(traceback.format_exc())

    # 获取房间号
    def get_room_id(self):
        return My_handle.config.get("room_display_id")


    # 音频合成处理
    def audio_synthesis_handle(self, data_json):
        logger.info("进入 audio_synthesis_handle")

        
        """音频合成处理

        Args:
            data_json (dict): 传递的json数据

            核心参数:
            type目前有
                reread_top_priority 最高优先级-复读
                talk 聊天（语音输入）
                comment 弹幕
                local_qa_text 本地问答文本
                local_qa_audio 本地问答音频
                song 歌曲
                reread 复读
                key_mapping 按键映射
                key_mapping_copywriting 按键映射-文案
                integral 积分
                read_comment 念弹幕
                gift 礼物
                entrance 用户入场
                follow 用户关注
                schedule 定时任务
                idle_time_task 闲时任务
                abnormal_alarm 异常报警
                image_recognition_schedule 图像识别定时任务

        """

        if "content" in data_json:
            if data_json['content']:
                # 替换文本内容中\n为空
                data_json['content'] = data_json['content'].replace('\n', '')

        My_handle.audio.audio_synthesis(data_json)
        logger.debug(f'data_json={data_json}')


    # 弹幕格式检查和特殊字符替换和指定语言过滤
    def comment_check_and_replace(self, content):
        """弹幕格式检查和特殊字符替换和指定语言过滤

        Args:
            content (str): 待处理的弹幕内容

        Returns:
            str: 处理完毕后的弹幕内容/None
        """

        # 全为标点符号
        if My_handle.common.is_punctuation_string(content):
            return None

        # 换行转为,
        content = content.replace('\n', ',')

        # 表情弹幕过滤
        if My_handle.config.get("filter", "emoji"):
            # 如b站的表情弹幕就是[表情名]的这种格式，采用正则表达式进行过滤
            content = re.sub(r'\[.*?\]', '', content)
            logger.info(f"表情弹幕过滤后：{content}")

        # 语言检测
        if My_handle.common.lang_check(content, My_handle.config.get("need_lang")) is None:
            logger.warning("语言检测不通过，已过滤")
            return None

        return content


    # 弹幕日志记录
    def write_to_comment_log(self, resp_content: str, data: dict):
        try:
            # 将 AI 回复记录到日志文件中
            with open(self.comment_file_path, "r+", encoding="utf-8") as f:
                tmp_content = f.read()
                # 将指针移到文件头部位置（此目的是为了让直播中读取日志文件时，可以一直让最新内容显示在顶部）
                f.seek(0, 0)
                # 不过这个实现方式，感觉有点低效
                # 设置单行最大字符数，主要目的用于接入直播弹幕显示时，弹幕过长导致的显示溢出问题
                max_length = 20
                resp_content_substrings = [resp_content[i:i + max_length] for i in range(0, len(resp_content), max_length)]
                resp_content_joined = '\n'.join(resp_content_substrings)

                # 根据 弹幕日志类型进行各类日志写入
                if My_handle.config.get("comment_log_type") == "问答":
                    f.write(f"[{data['username']} 提问]:\n{data['content']}\n[AI回复{data['username']}]:{resp_content_joined}\n" + tmp_content)
                elif My_handle.config.get("comment_log_type") == "问题":
                    f.write(f"[{data['username']} 提问]:\n{data['content']}\n" + tmp_content)
                elif My_handle.config.get("comment_log_type") == "回答":
                    f.write(f"[AI回复{data['username']}]:\n{resp_content_joined}\n" + tmp_content)
        except Exception as e:
            logger.error(traceback.format_exc())

 


    # 自定义命令处理
    def custom_cmd_handle(self, type, data):
        """自定义命令处理

        Args:
            type (str): 数据来源类型（弹幕/回复）
            data (dict): 平台侧传入的data数据，直接拿来做解析

        Returns:
            bool: 是否正常触发了自定义命令事件，是True 否False
        """
        flag = False


        try:
            if My_handle.config.get("custom_cmd", "enable"):
                # 判断传入的数据是否包含gift_name键值，有的话则是礼物数据
                if "gift_name" in data:
                    pass
                else:
                    username = data["username"]
                    content = data["content"]
                    custom_cmd_configs = My_handle.config.get("custom_cmd", "config")

                    for custom_cmd_config in custom_cmd_configs:
                        similarity = float(custom_cmd_config["similarity"])
                        for keyword in custom_cmd_config["keywords"]:
                            if type == "弹幕":
                                # 判断相似度
                                ratio = difflib.SequenceMatcher(None, content, keyword).ratio()
                                if ratio >= similarity:
                                    resp = My_handle.common.send_request(
                                        custom_cmd_config["api_url"], 
                                        custom_cmd_config["api_type"],
                                        resp_data_type=custom_cmd_config["resp_data_type"]
                                    )

                                    # 使用 eval() 执行字符串表达式并获取结果
                                    resp_content = eval(custom_cmd_config["data_analysis"])

                                    # 将字符串中的换行符替换为句号
                                    resp_content = resp_content.replace('\n', '。')

                                    logger.debug(f"resp_content={resp_content}")

                                    # 违禁词处理
                                    resp_content = self.prohibitions_handle(resp_content)
                                    if resp_content is None:
                                        return flag

                                    variables = {
                                        'keyword': keyword,
                                        'cur_time': My_handle.common.get_bj_time(5),
                                        'username': username,
                                        'data': resp_content
                                    }

                                    tmp = custom_cmd_config["resp_template"]

                                    # 使用字典进行字符串替换
                                    if any(var in tmp for var in variables):
                                        resp_content = tmp.format(**{var: value for var, value in variables.items() if var in tmp})
                                    
                                    # 音频合成时需要用到的重要数据
                                    message = {
                                        "type": "reread",
                                        "tts_type": My_handle.config.get("audio_synthesis_type"),
                                        "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                                        "config": My_handle.config.get("filter"),
                                        "username": username,
                                        "content": resp_content
                                    }

                                    logger.debug(message)
                                    
                                    logger.info(f'【触发 自定义命令】关键词：{keyword} 返回内容：{resp_content}')

                                    self.audio_synthesis_handle(message)

                                    self.webui_show_chat_log_callback("自定义命令", data, resp_content)

                                    flag = True
                                    
                            
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'【触发自定义命令】错误：{e}')

        return flag

    

    # 判断限定时间段内数据是否重复
    def is_data_repeat_in_limited_time(self, type: str=None, data: dict=None):
        """判断限定时间段内数据是否重复

        Args:
            type (str): 判断的数据类型（comment|gift|entrance)
            data (dict): 包含用户名,弹幕内容

        Returns:
            dict: 传递给音频合成的JSON数据
        """
        if My_handle.config.get("filter", "limited_time_deduplication", "enable"):
            logger.debug(f"限定时间段内数据重复 My_handle.live_data={My_handle.live_data}")
                        
            if type is not None and type != "" and data is not None:
                if type == "comment":
                    # 如果存在重复数据，返回True
                    for tmp in My_handle.live_data[type]:
                        if tmp['username'] == data['username'] and tmp['content'] == data['content']:
                            logger.debug(f"限定时间段内数据重复 type={type},data={data}")
                            return True
                elif type == "gift":
                    # 如果存在重复数据，返回True
                    for tmp in My_handle.live_data[type]:
                        if tmp['username'] == data['username']:
                            logger.debug(f"限定时间段内数据重复 type={type},data={data}")
                            return True
                elif type == "entrance":   
                    # 如果存在重复数据，返回True
                    for tmp in My_handle.live_data[type]:
                        if tmp['username'] == data['username']:
                            logger.debug(f"限定时间段内数据重复 type={type},data={data}")
                            return True
                
                # 不存在则插入，返回False
                My_handle.live_data[type].append(data)
        return False



    """                                                              
                                                                           
                                                         ,`                
                             @@@@`               =@@\`   /@@/              
                ,/@@] =@@@`  @@@/                 =@@\/@@@@@@@@@[          
           .\@@/[@@@@` ,@@@ =@/.             ,[[[[.=@^ ,@@@@\`             
                *@@^,`  .]]]@@@@@@\`          ,@@@@@@[[[. =@@@@.           
           .]]]]/@@`\@@/ *@@^  =@@@/           ,@@@@@@@@/`@@@`             
            =@@*    .@@@@@@@@/`@@@^             ,@@\]]/@@@@@.              
            =@@      =@@*.@@\]/@@^               ,\@@\   ,]]@@@@]          
          ,/@@@@@@@^  \@/[@@^               .@@@@@@@@@[[[\@\.              
          ,@/. .@@@      .@@\]/@@@@@@`          ,@@@,@@@.,]@@@`            
               .@@/@@@@@/[@@/                  /@@\]@@@@@@@@@@@@@]         
               =@@^      .@@^                ]@@@@@^ @@@  @@@ ,@@@@@@\].   
           ,]]/@@@`      .@@^             ./@/` .@@^.@@@/@@@/              
             \@@@`       .@@^                       .@@@ .[[               
                         .@@`                        @@^                   
                                                                                                                                          

    """

    # 弹幕处理 直播间的弹幕消息会统一到此函数进行处理
    def comment_handle(self, data):
        """弹幕处理 直播间的弹幕消息会统一到此函数进行处理

        Args:
            data (dict): 包含用户名,弹幕内容

        Returns:
            dict: 传递给音频合成的JSON数据
        """
        logger.info("进入 comment_handle")
        try:
            username = data["username"]
            content = data["content"]

            # 输出当前用户发送的弹幕消息
            logger.debug(f"[{username}]: {content}")

            # 限定时间数据去重
            if self.is_data_repeat_in_limited_time("comment", data):
                return None



            # 返回给webui的聊天记录
            if My_handle.config.get("talk", "show_chat_log"):
                if "ori_username" not in data:
                    data["ori_username"] = data["username"]
                if "ori_content" not in data:
                    data["ori_content"] = data["content"]
                if "user_face" not in data:
                    data["user_face"] = 'https://robohash.org/ui'

                # 返回给webui的数据
                return_webui_json = {
                    "type": "llm",
                    "data": {
                        "type": "弹幕信息",
                        "username": data["ori_username"],
                        "user_face": data["user_face"],
                        "content_type": "question",
                        "content": data["ori_content"],
                        "timestamp": My_handle.common.get_bj_time(0)
                    }
                }
                webui_ip = "127.0.0.1" if My_handle.config.get("webui", "ip") == "0.0.0.0" else My_handle.config.get("webui", "ip")
                tmp_json = My_handle.common.send_request(f'http://{webui_ip}:{My_handle.config.get("webui", "port")}/callback', "POST", return_webui_json, timeout=10)
            

            # 记录数据库
            if My_handle.config.get("database", "comment_enable"):
                insert_data_sql = '''
                INSERT INTO danmu (username, content, ts) VALUES (?, ?, ?)
                '''
                self.db.execute(insert_data_sql, (username, content, datetime.now()))

            # 合并字符串末尾连续的*  主要针对获取不到用户名的情况
            username = My_handle.common.merge_consecutive_asterisks(username)
     
            # 判断字符串是否全为标点符号，是的话就过滤
            if My_handle.common.is_punctuation_string(content):
                logger.debug(f"用户:{username}]，发送纯符号的弹幕，已过滤")
                return

            
            try:
                # 念弹幕
                if My_handle.config.get("read_comment", "enable"):
                    logger.debug(f"念弹幕 content:{content}")

                    # 音频合成时需要用到的重要数据
                    message = {
                        "type": "read_comment",
                        "tts_type": My_handle.config.get("audio_synthesis_type"),
                        "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                        "config": My_handle.config.get("filter"),
                        "username": username,
                        "content": content
                    }

                    # 判断是否需要念用户名
                    if My_handle.config.get("read_comment", "read_username_enable"):
                        # 将用户名中特殊字符替换为空
                        message['username'] = My_handle.common.replace_special_characters(message['username'], "！!@#￥$%^&*_-+/——=()（）【】}|{:;<>~`\\")
                        message['username'] = message['username'][:self.config.get("read_comment", "username_max_len")]

                        # 将用户名字符串中的数字转换成中文
                        if My_handle.config.get("filter", "username_convert_digits_to_chinese"):
                            message["username"] = My_handle.common.convert_digits_to_chinese(message["username"])
                            logger.debug(f"用户名字符串中的数字转换成中文：{message['username']}")

                        if len(self.config.get("read_comment", "read_username_copywriting")) > 0:
                            tmp_content = random.choice(self.config.get("read_comment", "read_username_copywriting"))
                            if "{username}" in tmp_content:
                                message['content'] = tmp_content.format(username=message['username']) + message['content']

                    # 是否启用了周期性触发功能，启用此功能后，数据会被缓存，之后周期到了才会触发
                    if My_handle.config.get("read_comment", "periodic_trigger", "enable"):
                        My_handle.task_data["read_comment"]["data"].append(message)
                    else:
                        self.audio_synthesis_handle(message)
            except Exception as e:
                logger.error(traceback.format_exc())

        

            # logger.info("resp_content=" + resp_content)

                

            # 音频合成时需要用到的重要数据
            message = {
                "type": "comment",
                "tts_type": My_handle.config.get("audio_synthesis_type"),
                "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                "config": My_handle.config.get("filter"),
                "username": username,
                "content": content
            }


            # 合成音频
            self.audio_synthesis_handle(message)

            return message
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 礼物处理
    def gift_handle(self, data):
        try:
            # 限定时间数据去重
            if self.is_data_repeat_in_limited_time("gift", data):
                return None
            
            # 记录数据库
            if My_handle.config.get("database", "gift_enable"):
                insert_data_sql = '''
                INSERT INTO gift (username, gift_name, gift_num, unit_price, total_price, ts) VALUES (?, ?, ?, ?, ?, ?)
                '''
                self.db.execute(insert_data_sql, (
                    data['username'], 
                    data['gift_name'], 
                    data['num'], 
                    data['unit_price'], 
                    data['total_price'],
                    datetime.now())
                )

            


            # 合并字符串末尾连续的*  主要针对获取不到用户名的情况
            data['username'] = My_handle.common.merge_consecutive_asterisks(data['username'])
            # 删除用户名中的特殊字符
            data['username'] = My_handle.common.replace_special_characters(data['username'], "！!@#￥$%^&*_-+/——=()（）【】}|{:;<>~`\\")  

            data['username'] = data['username'][:self.config.get("thanks", "username_max_len")]

            # 将用户名字符串中的数字转换成中文
            if My_handle.config.get("filter", "username_convert_digits_to_chinese"):
                data["username"] = My_handle.common.convert_digits_to_chinese(data["username"])

            # logger.debug(f"[{data['username']}]: {data}")
        
            if not My_handle.config.get("thanks")["gift_enable"]:
                return None

            # 如果礼物总价低于设置的礼物感谢最低值
            if data["total_price"] < My_handle.config.get("thanks")["lowest_price"]:
                return None

            if My_handle.config.get("thanks", "gift_random"):
                resp_content = random.choice(My_handle.config.get("thanks", "gift_copy"))
            else:
                # 类变量list中是否有数据，没有就拷贝下数据再顺序取出首个数据
                if len(My_handle.thanks_gift_copy) == 0:
                    if len(My_handle.config.get("thanks", "gift_copy")) == 0:
                        logger.warning("你把礼物的文案删了，还触发个der礼物感谢？不用别启用不就得了，删了搞啥")
                        return None
                resp_content = My_handle.thanks_gift_copy.pop(0)

            
            # 括号语法替换
            resp_content = My_handle.common.brackets_text_randomize(resp_content)
            
            # 动态变量替换
            data_json = {
                "username": data["username"],
                "gift_name": data["gift_name"],
                'gift_num': data["num"],
                'unit_price': data["unit_price"],
                'total_price': data["total_price"],
                'cur_time': My_handle.common.get_bj_time(5),
            } 
            resp_content = My_handle.common.dynamic_variable_replacement(resp_content, data_json)


            message = {
                "type": "gift",
                "tts_type": My_handle.config.get("audio_synthesis_type"),
                "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                "config": My_handle.config.get("filter"),
                "username": data["username"],
                "content": resp_content,
                "gift_info": data
            }

           

            # 是否启用了周期性触发功能，启用此功能后，数据会被缓存，之后周期到了才会触发
            if My_handle.config.get("thanks", "gift", "periodic_trigger", "enable"):
                My_handle.task_data["thanks"]["gift"]["data"].append(message)
            else:
                self.audio_synthesis_handle(message)

            return message
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 入场处理
    def entrance_handle(self, data):
        try:
            # 限定时间数据去重
            if self.is_data_repeat_in_limited_time("entrance", data):
                return None
            
            # 记录数据库
            if My_handle.config.get("database", "entrance_enable"):
                insert_data_sql = '''
                INSERT INTO entrance (username, ts) VALUES (?, ?)
                '''
                self.db.execute(insert_data_sql, (data['username'], datetime.now()))


            # 合并字符串末尾连续的*  主要针对获取不到用户名的情况
            data['username'] = My_handle.common.merge_consecutive_asterisks(data['username'])
            # 删除用户名中的特殊字符
            data['username'] = My_handle.common.replace_special_characters(data['username'], "！!@#￥$%^&*_-+/——=()（）【】}|{:;<>~`\\")

            data['username'] = data['username'][:self.config.get("thanks", "username_max_len")]

            # 将用户名字符串中的数字转换成中文
            if My_handle.config.get("filter", "username_convert_digits_to_chinese"):
                data["username"] = My_handle.common.convert_digits_to_chinese(data["username"])

            # logger.debug(f"[{data['username']}]: {data['content']}")
        
            if not My_handle.config.get("thanks")["entrance_enable"]:
                return None

            if My_handle.config.get("thanks", "entrance_random"):
                resp_content = random.choice(My_handle.config.get("thanks", "entrance_copy")).format(username=data["username"])
            else:
                # 类变量list中是否有数据，没有就拷贝下数据再顺序取出首个数据
                if len(My_handle.thanks_entrance_copy) == 0:
                    if len(My_handle.config.get("thanks", "entrance_copy")) == 0:
                        logger.warning("你把入场的文案删了，还触发个der入场感谢？不用别启用不就得了，删了搞啥")
                        return None
                    My_handle.thanks_entrance_copy = copy.copy(My_handle.config.get("thanks", "entrance_copy"))
                resp_content = My_handle.thanks_entrance_copy.pop(0).format(username=data["username"])

            # 括号语法替换
            resp_content = My_handle.common.brackets_text_randomize(resp_content)

            message = {
                "type": "entrance",
                "tts_type": My_handle.config.get("audio_synthesis_type"),
                "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                "config": My_handle.config.get("filter"),
                "username": data['username'],
                "content": resp_content
            }


            # 是否启用了周期性触发功能，启用此功能后，数据会被缓存，之后周期到了才会触发
            if My_handle.config.get("thanks", "entrance", "periodic_trigger", "enable"):
                My_handle.task_data["thanks"]["entrance"]["data"].append(message)
            else:
                self.audio_synthesis_handle(message)

            return message
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 关注处理
    def follow_handle(self, data):
        try:
            # 合并字符串末尾连续的*  主要针对获取不到用户名的情况
            data['username'] = My_handle.common.merge_consecutive_asterisks(data['username'])
            # 删除用户名中的特殊字符
            data['username'] = My_handle.common.replace_special_characters(data['username'], "！!@#￥$%^&*_-+/——=()（）【】}|{:;<>~`\\")

            data['username'] = data['username'][:self.config.get("thanks", "username_max_len")]


            # 将用户名字符串中的数字转换成中文
            if My_handle.config.get("filter", "username_convert_digits_to_chinese"):
                data["username"] = My_handle.common.convert_digits_to_chinese(data["username"])

            # logger.debug(f"[{data['username']}]: {data['content']}")
        
            if not My_handle.config.get("thanks")["follow_enable"]:
                return None

            if My_handle.config.get("thanks", "follow_random"):
                resp_content = random.choice(My_handle.config.get("thanks", "follow_copy")).format(username=data["username"])
            else:
                # 类变量list中是否有数据，没有就拷贝下数据再顺序取出首个数据
                if len(My_handle.thanks_follow_copy) == 0:
                    if len(My_handle.config.get("thanks", "follow_copy")) == 0:
                        logger.warning("你把关注的文案删了，还触发个der关注感谢？不用别启用不就得了，删了搞啥")
                        return None
                    My_handle.thanks_follow_copy = copy.copy(My_handle.config.get("thanks", "follow_copy"))
                resp_content = My_handle.thanks_follow_copy.pop(0).format(username=data["username"])
            
            # 括号语法替换
            resp_content = My_handle.common.brackets_text_randomize(resp_content)

            message = {
                "type": "follow",
                "tts_type": My_handle.config.get("audio_synthesis_type"),
                "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                "config": My_handle.config.get("filter"),
                "username": data['username'],
                "content": resp_content
            }

           
            

            # 是否启用了周期性触发功能，启用此功能后，数据会被缓存，之后周期到了才会触发
            if My_handle.config.get("thanks", "follow", "periodic_trigger", "enable"):
                My_handle.task_data["thanks"]["follow"]["data"].append(message)
            else:
                self.audio_synthesis_handle(message)

            return message
        except Exception as e:
            logger.error(traceback.format_exc())
            return None

    # 定时处理
    


    """
    数据丢弃部分
    增加新的处理事件时，需要进行这块部分的内容追加
    """
    def process_data(self, data, timer_flag):
        with self.data_lock:
            if timer_flag not in self.timers or not self.timers[timer_flag].is_alive():
                self.timers[timer_flag] = threading.Timer(self.get_interval(timer_flag), self.process_last_data, args=(timer_flag,))
                self.timers[timer_flag].start()

            # self.timers[timer_flag].last_data = data
            if hasattr(self.timers[timer_flag], 'last_data'):
                self.timers[timer_flag].last_data.append(data)
                # 这里需要注意配置命名!!!
                # 保留数据数量
            else:
                self.timers[timer_flag].last_data = [data]

    def process_last_data(self, timer_flag):
        with self.data_lock:
            timer = self.timers.get(timer_flag)
            if timer and timer.last_data is not None and timer.last_data != []:
                logger.debug(f"预处理定时器触发 type={timer_flag}，data={timer.last_data}")

                My_handle.is_handleing = 1

                if timer_flag == "comment":
                    for data in timer.last_data:
                        self.comment_handle(data)
                elif timer_flag == "gift":
                    for data in timer.last_data:
                        self.gift_handle(data)
                    #self.gift_handle(timer.last_data)
                elif timer_flag == "entrance":
                    for data in timer.last_data:
                        self.entrance_handle(data)
                    #self.entrance_handle(timer.last_data)
                elif timer_flag == "follow":
                    for data in timer.last_data:
                        self.follow_handle(data)

                My_handle.is_handleing = 0

                # 清空数据
                timer.last_data = []

    def get_interval(self, timer_flag):
        # 根据标志定义不同计时器的间隔
        intervals = {
            "comment": My_handle.config.get("filter", "comment_forget_duration"),
            "gift": My_handle.config.get("filter", "gift_forget_duration"),
            "entrance": My_handle.config.get("filter", "entrance_forget_duration"),
            "follow": My_handle.config.get("filter", "follow_forget_duration"),
            "talk": My_handle.config.get("filter", "talk_forget_duration"),
            "schedule": My_handle.config.get("filter", "schedule_forget_duration"),
            "idle_time_task": My_handle.config.get("filter", "idle_time_task_forget_duration")
            # 根据需要添加更多计时器及其间隔，记得添加config.json中的配置项
        }

        # 默认间隔为0.1秒
        return intervals.get(timer_flag, 0.1)


    """
    异常报警
    """ 
    def abnormal_alarm_handle(self, type):
        """异常报警

        Args:
            type (str): 报警类型

        Returns:
            bool: True/False
        """

        try:
            My_handle.abnormal_alarm_data[type]["error_count"] += 1

            if not My_handle.config.get("abnormal_alarm", type, "enable"):
                return True
            
            if My_handle.config.get("abnormal_alarm", type, "type") == "local_audio":
                # 是否错误数大于 自动重启错误数
                if My_handle.abnormal_alarm_data[type]["error_count"] >= My_handle.config.get("abnormal_alarm", type, "auto_restart_error_num"):
                    data = {
                        "type": "restart",
                        "api_type": "api",
                        "data": {
                            "config_path": "config.json"
                        }
                    }

                    webui_ip = "127.0.0.1" if My_handle.config.get("webui", "ip") == "0.0.0.0" else My_handle.config.get("webui", "ip")
                    My_handle.common.send_request(f'http://{webui_ip}:{My_handle.config.get("webui", "port")}/sys_cmd', "POST", data)

                # 是否错误数小于 开始报警错误数，是则不触发报警
                if My_handle.abnormal_alarm_data[type]["error_count"] < My_handle.config.get("abnormal_alarm", type, "start_alarm_error_num"):
                    return

                path_list = My_handle.common.get_all_file_paths(My_handle.config.get("abnormal_alarm", type, "local_audio_path"))

                # 随机选择列表中的一个元素
                audio_path = random.choice(path_list)

                message = {
                    "type": "abnormal_alarm",
                    "tts_type": My_handle.config.get("audio_synthesis_type"),
                    "data": My_handle.config.get(My_handle.config.get("audio_synthesis_type")),
                    "config": My_handle.config.get("filter"),
                    "username": "系统",
                    "content": os.path.join(My_handle.config.get("abnormal_alarm", type, "local_audio_path"), My_handle.common.extract_filename(audio_path, True))
                }

                logger.warning(f"【异常报警-{type}】 {My_handle.common.extract_filename(audio_path, False)}")

                self.audio_synthesis_handle(message)

        except Exception as e:
            logger.error(traceback.format_exc())

            return False

        return True

