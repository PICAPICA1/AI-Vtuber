import re
import threading
import asyncio
from copy import deepcopy
import aiohttp
import os, random
import copy
import traceback

from elevenlabs import generate, play, set_api_key

from pydub import AudioSegment

from .common import Common
from .my_log import logger
from .config import Config
from utils.audio_handle.my_tts import MY_TTS
from utils.audio_handle.audio_player import AUDIO_PLAYER


class Audio:
    # 文案播放标志 0手动暂停 1临时暂停  2循环播放
    copywriting_play_flag = -1

    # pygame.mixer实例
    mixer_normal = None
    mixer_copywriting = None

    # 全局变量用于保存恢复文案播放计时器对象
    unpause_copywriting_play_timer = None

    audio_player = None

    # 消息列表，存储待合成音频的json数据
    message_queue = []
    message_queue_lock = threading.Lock()
    message_queue_not_empty = threading.Condition(lock=message_queue_lock)
    # 创建待播放音频路径队列
    voice_tmp_path_queue = []
    voice_tmp_path_queue_lock = threading.Lock()
    voice_tmp_path_queue_not_empty = threading.Condition(lock=voice_tmp_path_queue_lock)
    # # 文案单独一个线程排队播放
    # only_play_copywriting_thread = None

    # 第一次触发voice_tmp_path_queue_not_empty标志
    voice_tmp_path_queue_not_empty_flag = False

    no_match_count = 0

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

    def __init__(self, config_path, type=1):
        self.config_path = config_path  
        self.config = Config(config_path)
        self.common = Common()
        self.my_tts = MY_TTS(config_path)

        # 文案模式
        if type == 2:
            logger.info("文案模式的Audio初始化...")
            return
    
        # 文案单独一个线程排队播放
        self.only_play_copywriting_thread = None

        if self.config.get("play_audio", "player") in ["pygame"]:
            import pygame

            # 初始化多个pygame.mixer实例
            Audio.mixer_normal = pygame.mixer
            Audio.mixer_copywriting = pygame.mixer

        # 旧版同步写法
        # threading.Thread(target=self.message_queue_thread).start()
        # 改异步
        threading.Thread(target=lambda: asyncio.run(self.message_queue_thread())).start()

        # 音频合成单独一个线程排队播放
        threading.Thread(target=lambda: asyncio.run(self.only_play_audio())).start()
        # self.only_play_audio_thread = threading.Thread(target=self.only_play_audio)
        # self.only_play_audio_thread.start()

        # 文案单独一个线程排队播放
        if self.only_play_copywriting_thread == None:
            # self.only_play_copywriting_thread = threading.Thread(target=lambda: asyncio.run(self.only_play_copywriting()))
            self.only_play_copywriting_thread = threading.Thread(target=self.start_only_play_copywriting)
            self.only_play_copywriting_thread.start()

        Audio.audio_player =  AUDIO_PLAYER(self.config.get("audio_player"))

        # 虚拟身体部分
        if self.config.get("visual_body") == "live2d-TTS-LLM-GPT-SoVITS-Vtuber":
            pass

    # 清空 待合成消息队列|待播放音频队列
    def clear_queue(self, type: str="message_queue"):
        """清空 待合成消息队列|待播放音频队列

        Args:
            type (str, optional): 队列类型. Defaults to "message_queue".

        Returns:
            bool: 清空结果
        """
        try:
            if type == "voice_tmp_path_queue":
                if len(Audio.voice_tmp_path_queue) == 0:
                    return True
                with self.voice_tmp_path_queue_lock:
                    Audio.voice_tmp_path_queue.clear()
                return True
            elif type == "message_queue":
                if len(Audio.message_queue) == 0:
                    return True
                with self.message_queue_lock:
                    Audio.message_queue.clear()
                return True
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"清空{type}队列失败：{e}")
            return False

    # 停止音频播放
    def stop_audio(self, type: str="pygame", mixer_normal: bool=True, mixer_copywriting: bool=True):
        try:
            if type == "pygame":
                if mixer_normal:
                    Audio.mixer_normal.music.stop()
                    logger.info("停止普通音频播放")
                if mixer_copywriting:
                    Audio.mixer_copywriting.music.stop()
                    logger.info("停止文案音频播放")
                return True
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"停止音频播放失败：{e}")
            return False
        

    # 判断 等待合成消息队列|待播放音频队列 数是否小于或大于某个值，就返回True
    def is_queue_less_or_greater_than(self, type: str="message_queue", less: int=None, greater: int=None):
        if less:
            if type == "voice_tmp_path_queue":
                if len(Audio.voice_tmp_path_queue) < less:
                    return True
                return False
            elif type == "message_queue":
                if len(Audio.message_queue) < less:
                    return True
                return False
        
        if greater:
            if type == "voice_tmp_path_queue":
                if len(Audio.voice_tmp_path_queue) > greater:
                    return True
                return False
            elif type == "message_queue":
                if len(Audio.message_queue) > greater:
                    return True
                return False
        
        return False
    
    def get_audio_info(self):
        return {
            "wait_play_audio_num": len(Audio.voice_tmp_path_queue),
            "wait_synthesis_msg_num": len(Audio.message_queue),
        }

    # 判断等待合成和已经合成的队列是否为空
    def is_audio_queue_empty(self):
        """判断等待合成和已经合成的队列是否为空

        Returns:
            int: 0 都不为空 | 1 message_queue 为空 | 2 voice_tmp_path_queue 为空 | 3 message_queue和voice_tmp_path_queue 为空 |
                 4 mixer_normal 不在播放 | 5 message_queue 为空、mixer_normal 不在播放 | 6 voice_tmp_path_queue 为空、mixer_normal 不在播放 |
                 7 message_queue和voice_tmp_path_queue 为空、mixer_normal 不在播放 | 8 mixer_copywriting 不在播放 | 9 message_queue 为空、mixer_copywriting 不在播放 |
                 10 voice_tmp_path_queue 为空、mixer_copywriting 不在播放 | 11 message_queue和voice_tmp_path_queue 为空、mixer_copywriting 不在播放 |
                 12 message_queue 为空、voice_tmp_path_queue 为空、mixer_normal 不在播放 | 13 message_queue 为空、voice_tmp_path_queue 为空、mixer_copywriting 不在播放 |
                 14 voice_tmp_path_queue为空、mixer_normal 不在播放、mixer_copywriting 不在播放 | 15 message_queue和voice_tmp_path_queue 为空、mixer_normal 不在播放、mixer_copywriting 不在播放 |
       
        """

        flag = 0

        # 判断队列是否为空
        if len(Audio.message_queue) == 0:
            flag += 1
        
        if len(Audio.voice_tmp_path_queue) == 0:
            flag += 2
        
        # TODO: 这一块仅在pygame播放下有效，但会对其他播放器模式下的功能造成影响，待优化
        if self.config.get("play_audio", "player") in ["pygame"]:
            # 检查mixer_normal是否正在播放
            if not Audio.mixer_normal.music.get_busy():
                flag += 4

            # 检查mixer_copywriting是否正在播放
            if not Audio.mixer_copywriting.music.get_busy():
                flag += 8

        return flag


    # 重载config
    def reload_config(self, config_path):
        self.config = Config(config_path)
        self.my_tts = MY_TTS(config_path)

    # 从指定文件夹中搜索指定文件，返回搜索到的文件路径
    def search_files(self, root_dir, target_file="", ignore_extension=False):
        matched_files = []

        # 如果忽略扩展名，只取目标文件的基本名
        target_for_comparison = os.path.splitext(target_file)[0] if ignore_extension else target_file

        for root, dirs, files in os.walk(root_dir):
            for file in files:
                # 根据 ignore_extension 判断是否要去除扩展名后再比较
                file_to_compare = os.path.splitext(file)[0] if ignore_extension else file

                if file_to_compare == target_for_comparison:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, root_dir)
                    relative_path = relative_path.replace("\\", "/")  # 将反斜杠替换为斜杠
                    matched_files.append(relative_path)

        return matched_files


    # 获取本地音频文件夹内所有的音频文件名
    def get_dir_audios_filename(self, audio_path, type=0):
        """获取本地音频文件夹内所有的音频文件名

        Args:
            audio_path (str): 音频文件路径
            type (int, 可选): 区分返回内容，0返回完整文件名，1返回文件名不含拓展名. 默认是0

        Returns:
            list: 文件名列表
        """
        try:
            # 使用 os.walk 遍历文件夹及其子文件夹
            audio_files = []
            for root, dirs, files in os.walk(audio_path):
                for file in files:
                    if file.endswith(('.mp3', '.wav', '.MP3', '.WAV', '.flac', '.aac', '.ogg', '.m4a')):
                        audio_files.append(os.path.join(root, file))

            # 提取文件名或保留完整文件名
            if type == 1:
                # 只返回文件名不含拓展名
                file_names = [os.path.splitext(os.path.basename(file))[0] for file in audio_files]
            else:
                # 返回完整文件名
                file_names = [os.path.basename(file) for file in audio_files]
                # 保留子文件夹路径
                # file_names = [os.path.relpath(file, audio_path) for file in audio_files]

            logger.debug("获取到本地音频文件名列表如下：")
            logger.debug(file_names)

            return file_names
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 音频合成消息队列线程
    async def message_queue_thread(self):
        logger.info("创建音频合成消息队列线程")
        while True:  # 无限循环，直到队列为空时退出
            try:
                # 获取线程锁，避免同时操作
                with Audio.message_queue_lock:
                    while not Audio.message_queue:
                        # 消费者在消费完一个消息后，如果列表为空，则调用wait()方法阻塞自己，直到有新消息到来
                        Audio.message_queue_not_empty.wait()  # 阻塞直到列表非空
                    message = Audio.message_queue.pop(0)
                logger.debug(message)

                # 此处的message数据，是等待合成音频的数据，此数据经过了优先级排队在此线程中被取出，即将进行音频合成。
                # 由于有些对接的项目自带音频播放功能，所以为保留相关机制的情况下做对接，此类型的对接源码应写于此处
                if self.config.get("visual_body") == "metahuman_stream":
                    logger.debug(f"合成音频前的原始数据：{message['content']}")
                    # 针对配置传参遗漏情况，主动补上，避免异常
                    if "config" not in message:
                        message["config"] = self.config.get("filter")
                    message["content"] = self.common.remove_extra_words(message["content"], message["config"]["max_len"], message["config"]["max_char_len"])
                    # logger.info("裁剪后的合成文本:" + text)

                    message["content"] = message["content"].replace('\n', '。')

                    if message["content"] != "":
                        await self.metahuman_stream_api(message['content'])
                else:
                    # 合成音频并插入待播放队列
                    await self.my_play_voice(message)

                # message = Audio.message_queue.get(block=True)
                # logger.debug(message)
                # await self.my_play_voice(message)
                # Audio.message_queue.task_done()

                # 加个延时 降低点edge-tts的压力
                # await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(traceback.format_exc())


    # 调用so-vits-svc的api
    async def so_vits_svc_api(self, audio_path=""):
        try:
            url = f"{self.config.get('so_vits_svc', 'api_ip_port')}/wav2wav"
            
            params = {
                "audio_path": audio_path,
                "tran": self.config.get("so_vits_svc", "tran"),
                "spk": self.config.get("so_vits_svc", "spk"),
                "wav_format": self.config.get("so_vits_svc", "wav_format")
            }

            # logger.info(params)

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=params) as response:
                    if response.status == 200:
                        file_name = 'so-vits-svc_' + self.common.get_bj_time(4) + '.wav'

                        voice_tmp_path = self.common.get_new_audio_path(self.config.get("play_audio", "out_path"), file_name)
                        
                        with open(voice_tmp_path, 'wb') as file:
                            file.write(await response.read())

                        logger.debug(f"so-vits-svc转换完成，音频保存在：{voice_tmp_path}")

                        return voice_tmp_path
                    else:
                        logger.error(await response.text())

                        return None
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 调用ddsp_svc的api
    async def ddsp_svc_api(self, audio_path=""):
        try:
            url = f"{self.config.get('ddsp_svc', 'api_ip_port')}/voiceChangeModel"
                
            # 读取音频文件
            with open(audio_path, "rb") as file:
                audio_file = file.read()

            data = aiohttp.FormData()
            data.add_field('sample', audio_file)
            data.add_field('fSafePrefixPadLength', str(self.config.get('ddsp_svc', 'fSafePrefixPadLength')))
            data.add_field('fPitchChange', str(self.config.get('ddsp_svc', 'fPitchChange')))
            data.add_field('sSpeakId', str(self.config.get('ddsp_svc', 'sSpeakId')))
            data.add_field('sampleRate', str(self.config.get('ddsp_svc', 'sampleRate')))

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    # 检查响应状态
                    if response.status == 200:
                        file_name = 'ddsp-svc_' + self.common.get_bj_time(4) + '.wav'

                        voice_tmp_path = self.common.get_new_audio_path(self.config.get("play_audio", "out_path"), file_name)
                        
                        with open(voice_tmp_path, 'wb') as file:
                            file.write(await response.read())

                        logger.debug(f"ddsp-svc转换完成，音频保存在：{voice_tmp_path}")

                        return voice_tmp_path
                    else:
                        logger.error(f"请求ddsp-svc失败，状态码：{response.status}")
                        return None

        except Exception as e:
            logger.error(traceback.format_exc())
            return None
        

    # 调用xuniren的api
    async def xuniren_api(self, audio_path=""):
        try:
            url = f"{self.config.get('xuniren', 'api_ip_port')}/audio_to_video?file_path={os.path.abspath(audio_path)}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    # 检查响应状态
                    if response.status == 200:
                        logger.info(f"xuniren合成完成")

                        return True
                    else:
                        logger.error(f"xuniren合成失败，状态码：{response.status}")
                        return False

        except Exception as e:
            logger.error(traceback.format_exc())
            return False

    # 调用EasyAIVtuber的api
    async def EasyAIVtuber_api(self, audio_path=""):
        try:
            from urllib.parse import urljoin

            url = urljoin(self.config.get('EasyAIVtuber', 'api_ip_port'), "/alive")
            
            data = {
                "type": "speak",  # 说话动作
                "speech_path": os.path.abspath(audio_path)
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    # 检查响应状态
                    if response.status == 200:
                        # 使用await等待异步获取JSON响应
                        json_response = await response.json()
                        logger.info(f"EasyAIVtuber发送成功，返回：{json_response['status']}")

                        return True
                    else:
                        logger.error(f"EasyAIVtuber发送失败，状态码：{response.status}")
                        return False

        except Exception as e:
            logger.error(traceback.format_exc())
            return False

    # 调用metahuman_stream的api
    async def metahuman_stream_api(self, message=""):
        try:
            from urllib.parse import urljoin

            url = urljoin(self.config.get('metahuman_stream', 'api_ip_port'), "/human")

            data = {
                "type": 'echo',
                "text": message
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    # 检查响应状态
                    if response.status == 200:
                        logger.info("metahuman发送成功")
                        return True
                    else:
                        logger.error(f"metahuman发送失败，状态码：{response.status}")
                        return False

        except Exception as e:
            logger.error(traceback.format_exc())
            return False
    
    # 调用digital_human_video_player的api
    async def digital_human_video_player_api(self, audio_path=""):
        try:
            from urllib.parse import urljoin

            url = urljoin(self.config.get('digital_human_video_player', 'api_ip_port'), "/show")
            
            data = {
                "type": self.config.get('digital_human_video_player', 'type'),
                "audio_path": os.path.abspath(audio_path),
                "video_path": "",
                "insert_index": -1
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    # 检查响应状态
                    if response.status == 200:
                        # 使用await等待异步获取JSON响应
                        json_response = await response.json()
                        logger.info(f"digital_human_video_player发送成功，返回：{json_response['message']}")

                        return True
                    else:
                        logger.error(f"digital_human_video_player发送失败，状态码：{response.status}")
                        return False

        except Exception as e:
            logger.error(traceback.format_exc())
            return False

    # 调用live2d_TTS_LLM_GPT_SoVITS_Vtuber的api
    async def live2d_TTS_LLM_GPT_SoVITS_Vtuber_api(self, audio_path=""):
        try:
            from urllib.parse import urljoin

            url = urljoin(self.config.get('live2d_TTS_LLM_GPT_SoVITS_Vtuber', 'api_ip_port'), "/ws")
            resp_json = self.common.get_filename_from_path(audio_path)
            if resp_json["code"] == 200:
                audio_url = urljoin(f"http://{self.config.get('webui', 'ip')}:{self.config.get('webui', 'port')}", f"/out/{resp_json['data']}")
            else:
                logger.error(f"live2d_TTS_LLM_GPT_SoVITS_Vtuber获取音频失败，返回：{resp_json['error']}")
                return False
            
            data = {
                "action": "talk",
                "data": {
                    "audio_path": audio_url
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    # 检查响应状态
                    if response.status == 200:
                        # 使用await等待异步获取JSON响应
                        json_response = await response.json()
                        logger.info(f"live2d_TTS_LLM_GPT_SoVITS_Vtuber发送成功，返回：{json_response['message']}")

                        return True
                    else:
                        logger.error(f"live2d_TTS_LLM_GPT_SoVITS_Vtuber发送失败，状态码：{response.status}")
                        return False

        except Exception as e:
            logger.error(traceback.format_exc())
            return False

    # 数据根据优先级排队插入待合成音频队列
    def data_priority_insert(self, type:str="等待合成消息", data_json:dict=None):
        """
        数据根据优先级排队插入待合成音频队列

        type目前有
            reread_top_priority 最高优先级-复读
            talk 聊天（语音输入）
            comment 弹幕
            local_qa_audio 本地问答音频
            song 歌曲
            reread 复读
            key_mapping 按键映射
            integral 积分
            read_comment 念弹幕
            gift 礼物
            entrance 用户入场
            follow 用户关注
            schedule 定时任务
            idle_time_task 闲时任务
            abnormal_alarm 异常报警
            image_recognition_schedule 图像识别定时任务
            trends_copywriting 动态文案
            assistant_anchor_text 助播-文本
            assistant_anchor_audio 助播-音频
        """
        logger.debug(f"message_queue: {Audio.message_queue}")
        logger.debug(f"data_json: {data_json}")

        # 定义 type 到优先级的映射，相同优先级的 type 映射到相同的值，值越大优先级越高
        priority_mapping = self.config.get("filter", "priority_mapping")
        
        def get_priority_level(data_json):
            """根据 data_json 的 'type' 键返回优先级，未定义的 type 或缺失 'type' 键将返回 None"""
            # 检查 data_json 是否包含 'type' 键且该键的值在 priority_mapping 中
            audio_type = data_json.get("type")
            return priority_mapping.get(audio_type, None)

        # 查找插入位置
        new_data_priority = get_priority_level(data_json)

        if type == "等待合成消息":
            logger.info(f"{type} 优先级: {new_data_priority} 内容：【{data_json['content']}】")

            # 如果新数据没有 'type' 键或其类型不在 priority_mapping 中，直接插入到末尾
            if new_data_priority is None:
                insert_position = len(Audio.message_queue)
            else:
                insert_position = 0  # 默认插入到列表开头
                # 从列表的最后一个元素开始，向前遍历列表，直到第一个元素
                for i in range(len(Audio.message_queue) - 1, -1, -1):
                    priority_level = get_priority_level(Audio.message_queue[i])
                    if priority_level is not None:
                        item_priority = int(priority_level)
                        # 确保比较时排除未定义类型的元素
                        if item_priority is not None and item_priority >= new_data_priority:
                            # 如果找到一个元素，其优先级小于或等于新数据，则将新数据插入到此元素之后
                            insert_position = i + 1
                            break
            
            logger.debug(f"insert_position={insert_position}")

            # 数据队列数据量超长判断，插入位置索引大于最大数，则说明优先级低与队列中已存在数据，丢弃数据
            if insert_position >= int(self.config.get("filter", "message_queue_max_len")):
                logger.info(f"message_queue 已满，数据丢弃：【{data_json['content']}】")
                return {"code": 1, "msg": f"message_queue 已满，数据丢弃：【{data_json['content']}】"}

            # 获取线程锁，避免同时操作
            with Audio.message_queue_lock:
                # logger.warning(f"插入前 message_queue={Audio.message_queue}")
                # 在计算出的位置插入新数据
                Audio.message_queue.insert(insert_position, data_json)
                # 生产者通过notify()通知消费者列表中有新的消息
                Audio.message_queue_not_empty.notify()
                # logger.warning(f"插入后 message_queue={Audio.message_queue}")

            return {"code": 200, "msg": f"数据已插入到位置 {insert_position}"}
        else:
            logger.info(f"{type} 优先级: {new_data_priority} 音频={data_json['voice_path']}")

            # 如果新数据没有 'type' 键或其类型不在 priority_mapping 中，直接插入到末尾
            if new_data_priority is None:
                insert_position = len(Audio.voice_tmp_path_queue)
            else:
                insert_position = 0  # 默认插入到列表开头
                # 从列表的最后一个元素开始，向前遍历列表，直到第一个元素
                for i in range(len(Audio.voice_tmp_path_queue) - 1, -1, -1):
                    priority_level = get_priority_level(Audio.voice_tmp_path_queue[i])
                    if priority_level is not None:
                        item_priority = int(priority_level)
                        # 确保比较时排除未定义类型的元素
                        if item_priority is not None and item_priority >= new_data_priority:
                            # 如果找到一个元素，其优先级小于或等于新数据，则将新数据插入到此元素之后
                            insert_position = i + 1
                            break
            
            logger.debug(f"insert_position={insert_position}")

            # 数据队列数据量超长判断，插入位置索引大于最大数，则说明优先级低与队列中已存在数据，丢弃数据
            if insert_position >= int(self.config.get("filter", "voice_tmp_path_queue_max_len")):
                logger.info(f"voice_tmp_path_queue 已满，音频丢弃：【{data_json['voice_path']}】")
                return {"code": 1, "msg": f"voice_tmp_path_queue 已满，音频丢弃：【{data_json['voice_path']}】"}

            # 获取线程锁，避免同时操作
            with Audio.voice_tmp_path_queue_lock:
                # 在计算出的位置插入新数据
                Audio.voice_tmp_path_queue.insert(insert_position, data_json)

                # 待播放音频数量大于首次播放阈值 且 处于首次播放情况下：
                if len(Audio.voice_tmp_path_queue) >= int(self.config.get("filter", "voice_tmp_path_queue_min_start_play")) and \
                    Audio.voice_tmp_path_queue_not_empty_flag is False:
                    Audio.voice_tmp_path_queue_not_empty_flag = True
                    # 生产者通过notify()通知消费者列表中有新的消息
                    Audio.voice_tmp_path_queue_not_empty.notify()
                # 非首次触发情况下，有数据就触发消费者播放
                elif Audio.voice_tmp_path_queue_not_empty_flag:
                    # 生产者通过notify()通知消费者列表中有新的消息
                    Audio.voice_tmp_path_queue_not_empty.notify()

            return {"code": 200, "msg": f"音频已插入到位置 {insert_position}"}

    # 音频合成（edge-tts / vits_fast等）并播放
    def audio_synthesis(self, message):
        try:
            logger.debug(message)

            # TTS类型为 none 时不合成音频
            if self.config.get("audio_synthesis_type") == "none":
                return

            # 将用户名字符串中的数字转换成中文
            if self.config.get("filter", "username_convert_digits_to_chinese"):
                if message["username"] is not None:
                    message["username"] = self.common.convert_digits_to_chinese(message["username"])

            # 判断是否是点歌模式
            if message['type'] == "song":
                # 拼接json数据，存入队列
                data_json = {
                    "type": message['type'],
                    "tts_type": "none",
                    "voice_path": message['content'],
                    "content": message["content"]
                }

                if "insert_index" in data_json:
                    data_json["insert_index"] = message["insert_index"]

                # 是否开启了音频播放 
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("等待合成消息", data_json)
                return
            # 异常报警
            elif message['type'] == "abnormal_alarm":
                # 拼接json数据，存入队列
                data_json = {
                    "type": message['type'],
                    "tts_type": "none",
                    "voice_path": message['content'],
                    "content": message["content"]
                }

                if "insert_index" in data_json:
                    data_json["insert_index"] = message["insert_index"]

                # 是否开启了音频播放 
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("等待合成消息", data_json)
                return
            # 是否为本地问答音频
            elif message['type'] == "local_qa_audio":
                # 拼接json数据，存入队列
                data_json = {
                    "type": message['type'],
                    "tts_type": "none",
                    "voice_path": message['file_path'],
                    "content": message["content"]
                }

                if "insert_index" in data_json:
                    data_json["insert_index"] = message["insert_index"]

                # 是否开启了音频播放
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("等待合成消息", data_json)
                return
            # 是否为助播-本地问答音频
            elif message['type'] == "assistant_anchor_audio":
                # 拼接json数据，存入队列
                data_json = {
                    "type": message['type'],
                    "tts_type": "none",
                    "voice_path": message['file_path'],
                    "content": message["content"]
                }

                if "insert_index" in data_json:
                    data_json["insert_index"] = message["insert_index"]

                # 是否开启了音频播放
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("等待合成消息", data_json)
                return

            # 闲时任务
            elif message['type'] == "idle_time_task":
                if message['content_type'] in ["comment", "reread"]:
                    pass
                elif message['content_type'] == "local_audio":
                    # 拼接json数据，存入队列
                    data_json = {
                        "type": message['type'],
                        "tts_type": "none",
                        "voice_path": message['file_path'],
                        "content": message["content"]
                    }

                    if "insert_index" in data_json:
                        data_json["insert_index"] = message["insert_index"]
                    
                    self.data_priority_insert("等待合成消息", data_json)

                    return
            # 按键映射 本地音频
            elif message['type'] == "key_mapping" and "file_path" in message:
                # 拼接json数据，存入队列
                data_json = {
                    "type": message['type'],
                    "tts_type": "none",
                    "voice_path": message['file_path'],
                    "content": message["content"]
                }

                if "insert_index" in data_json:
                    data_json["insert_index"] = message["insert_index"]

                # 是否开启了音频播放
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("等待合成消息", data_json)
                return

            # 是否语句切分
            if self.config.get("play_audio", "text_split_enable"):
                sentences = self.common.split_sentences(message['content'])
                for s in sentences:
                    message_copy = deepcopy(message)  # 创建 message 的副本
                    message_copy["content"] = s  # 修改副本的 content
                    logger.debug(f"s={s}")
                    if not self.common.is_all_space_and_punct(s):
                        self.data_priority_insert("等待合成消息", message_copy)  # 将副本放入队列中
            else:
                self.data_priority_insert("等待合成消息", message)
            

            # 单独开线程播放
            # threading.Thread(target=self.my_play_voice, args=(type, data, config, content,)).start()
        except Exception as e:
            logger.error(traceback.format_exc())
            return


    # 音频变声 so-vits-svc + ddsp
    async def voice_change(self, voice_tmp_path):
        """音频变声 so-vits-svc + ddsp

        Args:
            voice_tmp_path (str): 待变声音频路径

        Returns:
            str: 变声后的音频路径
        """
        # 转换为绝对路径
        voice_tmp_path = os.path.abspath(voice_tmp_path)

        # 是否启用ddsp-svc来变声
        if True == self.config.get("ddsp_svc", "enable"):
            voice_tmp_path = await self.ddsp_svc_api(audio_path=voice_tmp_path)
            if voice_tmp_path:
                logger.info(f"ddsp-svc合成成功，输出到={voice_tmp_path}")
            else:
                logger.error(f"ddsp-svc合成失败，请检查配置")
                self.abnormal_alarm_handle("svc")
                return None

        # 转换为绝对路径
        voice_tmp_path = os.path.abspath(voice_tmp_path)

        # 是否启用so-vits-svc来变声
        if True == self.config.get("so_vits_svc", "enable"):
            voice_tmp_path = await self.so_vits_svc_api(audio_path=voice_tmp_path)
            if voice_tmp_path:
                logger.info(f"so_vits_svc合成成功，输出到={voice_tmp_path}")
            else:
                logger.error(f"so_vits_svc合成失败，请检查配置")
                self.abnormal_alarm_handle("svc")
                
                return None
        
        return voice_tmp_path
    

    # 根据本地配置，使用TTS进行音频合成，返回相关数据
    async def tts_handle(self, message):
        """根据本地配置，使用TTS进行音频合成，返回相关数据

        Args:
            message (dict): json数据，含tts配置，tts类型

            例如：
            {
                'type': 'reread', 
                'tts_type': 'gpt_sovits', 
                'data': {'type': 'api', 'ws_ip_port': 'ws://localhost:9872/queue/join', 'api_ip_port': 'http://127.0.0.1:9880', 'ref_audio_path': 'F:\\\\GPT-SoVITS\\\\raws\\\\ikaros\\\\21.wav', 'prompt_text': 'マスター、どうりょくろか、いいえ、なんでもありません', 'prompt_language': '日文', 'language': '自动识别', 'cut': '凑四句一切', 'gpt_model_path': 'F:\\GPT-SoVITS\\GPT_weights\\ikaros-e15.ckpt', 'sovits_model_path': 'F:\\GPT-SoVITS\\SoVITS_weights\\ikaros_e8_s280.pth', 'webtts': {'api_ip_port': 'http://127.0.0.1:8080', 'spk': 'sanyueqi', 'lang': 'zh', 'speed': '1.0', 'emotion': '正常'}}, 
                'config': {
                    'before_must_str': [], 'after_must_str': [], 'before_filter_str': ['#'], 'after_filter_str': ['#'], 
                    'badwords': {'enable': True, 'discard': False, 'path': 'data/badwords.txt', 'bad_pinyin_path': 'data/违禁拼音.txt', 'replace': '*'}, 
                    'emoji': False, 'max_len': 80, 'max_char_len': 200, 
                    'comment_forget_duration': 1.0, 'comment_forget_reserve_num': 1, 'gift_forget_duration': 5.0, 'gift_forget_reserve_num': 1, 'entrance_forget_duration': 5.0, 'entrance_forget_reserve_num': 2, 'follow_forget_duration': 3.0, 'follow_forget_reserve_num': 1, 'talk_forget_duration': 0.1, 'talk_forget_reserve_num': 1, 'schedule_forget_duration': 0.1, 'schedule_forget_reserve_num': 1, 'idle_time_task_forget_duration': 0.1, 'idle_time_task_forget_reserve_num': 1, 'image_recognition_schedule_forget_duration': 0.1, 'image_recognition_schedule_forget_reserve_num': 1}, 
                'username': '主人', 
                'content': '你好'
            }

        Returns:
            dict: json数据，含tts配置，tts类型，合成结果等信息
        """

        try:
            if message["tts_type"] == "vits":
                # 语言检测
                language = self.common.lang_check(message["content"])

                logger.debug(f"message['content']={message['content']}")

                # 自定义语言名称（需要匹配请求解析）
                language_name_dict = {"en": "英文", "zh": "中文", "jp": "日文"}  

                if language in language_name_dict:
                    language = language_name_dict[language]
                else:
                    language = "自动"  # 无法识别出语言代码时的默认值

                # logger.info("language=" + language)

                data = {
                    "type": message["data"]["type"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "id": message["data"]["id"],
                    "format": message["data"]["format"],
                    "lang": language,
                    "length": message["data"]["length"],
                    "noise": message["data"]["noise"],
                    "noisew": message["data"]["noisew"],
                    "max": message["data"]["max"],
                    "sdp_radio": message["data"]["sdp_radio"],
                    "content": message["content"],
                    "gpt_sovits": message["data"]["gpt_sovits"],
                }

                # 调用接口合成语音
                voice_tmp_path = await self.my_tts.vits_api(data)
            
            elif message["tts_type"] == "bert_vits2":
                if message["data"]["language"] == "auto":
                    # 自动检测语言
                    language = self.common.lang_check(message["content"])

                    logger.debug(f'language={language}')

                    # 自定义语言名称（需要匹配请求解析）
                    language_name_dict = {"en": "EN", "zh": "ZH", "ja": "JP"}  

                    if language in language_name_dict:
                        language = language_name_dict[language]
                    else:
                        language = "ZH"  # 无法识别出语言代码时的默认值
                else:
                    language = message["data"]["language"]

                data = {
                    "api_ip_port": message["data"]["api_ip_port"],
                    "type": message["data"]["type"],
                    "model_id": message["data"]["model_id"],
                    "speaker_name": message["data"]["speaker_name"],
                    "speaker_id": message["data"]["speaker_id"],
                    "language": language,
                    "length": message["data"]["length"],
                    "noise": message["data"]["noise"],
                    "noisew": message["data"]["noisew"],
                    "sdp_radio": message["data"]["sdp_radio"],
                    "auto_translate": message["data"]["auto_translate"],
                    "auto_split": message["data"]["auto_split"],
                    "emotion": message["data"]["emotion"],
                    "style_text": message["data"]["style_text"],
                    "style_weight": message["data"]["style_weight"],
                    "刘悦-中文特化API": message["data"]["刘悦-中文特化API"],
                    "content": message["content"]
                }


                # 调用接口合成语音
                voice_tmp_path = await self.my_tts.bert_vits2_api(data)
            
            elif message["tts_type"] == "vits_fast":
                if message["data"]["language"] == "自动识别":
                    # 自动检测语言
                    language = self.common.lang_check(message["content"])

                    logger.debug(f'language={language}')

                    # 自定义语言名称（需要匹配请求解析）
                    language_name_dict = {"en": "English", "zh": "简体中文", "ja": "日本語"}  

                    if language in language_name_dict:
                        language = language_name_dict[language]
                    else:
                        language = "简体中文"  # 无法识别出语言代码时的默认值
                else:
                    language = message["data"]["language"]

                # logger.info("language=" + language)

                data = {
                    "api_ip_port": message["data"]["api_ip_port"],
                    "character": message["data"]["character"],
                    "speed": message["data"]["speed"],
                    "language": language,
                    "content": message["content"]
                }

                # 调用接口合成语音
                voice_tmp_path = self.my_tts.vits_fast_api(data)
                # logger.info(data_json)
            elif message["tts_type"] == "edge-tts":
                data = {
                    "content": message["content"],
                    "edge-tts": message["data"]
                }

                # 调用接口合成语音
                voice_tmp_path = await self.my_tts.edge_tts_api(data)
            elif message["tts_type"] == "elevenlabs":
                # 如果配置了密钥就设置上0.0
                if message["data"]["api_key"] != "":
                    set_api_key(message["data"]["api_key"])

                audio = generate(
                    text=message["content"],
                    voice=message["data"]["voice"],
                    model=message["data"]["model"]
                )

                play(audio)
                logger.info(f"elevenlabs合成内容：【{message['content']}】")

                return
            elif message["tts_type"] == "genshinvoice_top":
                voice_tmp_path = await self.my_tts.genshinvoice_top_api(message["content"])
            elif message["tts_type"] == "tts_ai_lab_top":
                voice_tmp_path = await self.my_tts.tts_ai_lab_top_api(message["content"])
            elif message["tts_type"] == "bark_gui":
                data = {
                    "api_ip_port": message["data"]["api_ip_port"],
                    "spk": message["data"]["spk"],
                    "generation_temperature": message["data"]["generation_temperature"],
                    "waveform_temperature": message["data"]["waveform_temperature"],
                    "end_of_sentence_probability": message["data"]["end_of_sentence_probability"],
                    "quick_generation": message["data"]["quick_generation"],
                    "seed": message["data"]["seed"],
                    "batch_count": message["data"]["batch_count"],
                    "content": message["content"]
                }

                # 调用接口合成语音
                voice_tmp_path = self.my_tts.bark_gui_api(data)
            elif message["tts_type"] == "vall_e_x":
                data = {
                    "api_ip_port": message["data"]["api_ip_port"],
                    "language": message["data"]["language"],
                    "accent": message["data"]["accent"],
                    "voice_preset": message["data"]["voice_preset"],
                    "voice_preset_file_path": message["data"]["voice_preset_file_path"],
                    "content": message["content"]
                }

                # 调用接口合成语音
                voice_tmp_path = self.my_tts.vall_e_x_api(data)
            elif message["tts_type"] == "openai_tts":
                data = {
                    "type": message["data"]["type"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "model": message["data"]["model"],
                    "voice": message["data"]["voice"],
                    "api_key": message["data"]["api_key"],
                    "content": message["content"]
                }

                # 调用接口合成语音
                voice_tmp_path = self.my_tts.openai_tts_api(data)
            elif message["tts_type"] == "reecho_ai":
                voice_tmp_path = await self.my_tts.reecho_ai_api(message["content"])
            elif message["tts_type"] == "gradio_tts":
                data = {
                    "request_parameters": message["data"]["request_parameters"],
                    "content": message["content"]
                }

                voice_tmp_path = self.my_tts.gradio_tts_api(data)  
            elif message["tts_type"] == "gpt_sovits":
                if message["data"]["language"] == "自动识别":
                    # 自动检测语言
                    language = self.common.lang_check(message["content"])

                    logger.debug(f'language={language}')

                    # 自定义语言名称（需要匹配请求解析）
                    language_name_dict = {"en": "英文", "zh": "中文", "ja": "日文"}  

                    if language in language_name_dict:
                        language = language_name_dict[language]
                    else:
                        language = "中文"  # 无法识别出语言代码时的默认值
                else:
                    language = message["data"]["language"]

                if message["data"]["api_0322"]["text_lang"] == "自动识别":
                    # 自动检测语言
                    language = self.common.lang_check(message["content"])

                    logger.debug(f'language={language}')

                    # 自定义语言名称（需要匹配请求解析）
                    language_name_dict = {"en": "英文", "zh": "中文", "ja": "日文"}  

                    if language in language_name_dict:
                        message["data"]["api_0322"]["text_lang"] = language_name_dict[language]
                    else:
                        message["data"]["api_0322"]["text_lang"] = "中文"  # 无法识别出语言代码时的默认值

                if message["data"]["api_0706"]["text_language"] == "自动识别":
                    message["data"]["api_0706"]["text_language"] = "auto"

                data = {
                    "type": message["data"]["type"],
                    "gradio_ip_port": message["data"]["gradio_ip_port"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "ref_audio_path": message["data"]["ref_audio_path"],
                    "prompt_text": message["data"]["prompt_text"],
                    "prompt_language": message["data"]["prompt_language"],
                    "language": language,
                    "cut": message["data"]["cut"],
                    "api_0322": message["data"]["api_0322"],
                    "api_0706": message["data"]["api_0706"],
                    "v2_api_0821": message["data"]["v2_api_0821"],
                    "webtts": message["data"]["webtts"],
                    "content": message["content"]
                }

                voice_tmp_path = await self.my_tts.gpt_sovits_api(data)  
            elif message["tts_type"] == "clone_voice":
                data = {
                    "type": message["data"]["type"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "voice": message["data"]["voice"],
                    "language": message["data"]["language"],
                    "speed": message["data"]["speed"],
                    "content": message["content"]
                }

                voice_tmp_path = await self.my_tts.clone_voice_api(data)
            elif message["tts_type"] == "azure_tts":
                data = {
                    "subscription_key": message["data"]["subscription_key"],
                    "region": message["data"]["region"],
                    "voice_name": message["data"]["voice_name"],
                    "content": message["content"]
                }

                voice_tmp_path = self.my_tts.azure_tts_api(data) 
            elif message["tts_type"] == "fish_speech":
                data = message["data"]

                if data["type"] == "web":
                    data["web"]["content"] = message["content"]
                    voice_tmp_path = await self.my_tts.fish_speech_web_api(data["web"])
                else:
                    data["tts_config"]["text"] = message["content"]
                    data["api_1.1.0"]["text"] = message["content"]
                    voice_tmp_path = await self.my_tts.fish_speech_api(data)
            elif message["tts_type"] == "chattts":
                logger.info(message)
                data = {
                    "type": message["data"]["type"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "gradio_ip_port": message["data"]["gradio_ip_port"],
                    "top_p": message["data"]["top_p"],
                    "top_k": message["data"]["top_k"],
                    "temperature": message["data"]["temperature"],
                    "text_seed_input": message["data"]["text_seed_input"],
                    "audio_seed_input": message["data"]["audio_seed_input"],
                    "refine_text_flag": message["data"]["refine_text_flag"],
                    "content": message["content"],
                    "api": message["data"]["api"],
                }

                voice_tmp_path = await self.my_tts.chattts_api(data)  
            elif message["tts_type"] == "cosyvoice":
                logger.debug(message)
                data = {
                    "type": message["data"]["type"],
                    "gradio_ip_port": message["data"]["gradio_ip_port"],
                    "api_ip_port": message["data"]["api_ip_port"],
                    "gradio_0707": message["data"]["gradio_0707"],
                    "api_0819": message["data"]["api_0819"],
                    "api": message["data"]["api"],
                    "content": message["content"],
                }

                voice_tmp_path = await self.my_tts.cosyvoice_api(data)  
            elif message["tts_type"] == "f5_tts":
                logger.debug(message)
                data = {
                    "type": message["data"]["type"],
                    "gradio_ip_port": message["data"]["gradio_ip_port"],
                    "ref_audio_orig": message["data"]["ref_audio_orig"],
                    "ref_text": message["data"]["ref_text"],
                    "model": message["data"]["model"],
                    "remove_silence": message["data"]["remove_silence"],
                    "cross_fade_duration": message["data"]["cross_fade_duration"],
                    "speed": message["data"]["speed"],
                    "content": message["content"],
                }

                voice_tmp_path = await self.my_tts.f5_tts_api(data)  
            elif message["tts_type"] == "multitts":
                data = {
                    "content": message["content"],
                    "multitts": message["data"]
                }

                voice_tmp_path = await self.my_tts.multitts_api(data)  
            elif message["tts_type"] == "melotts":
                data = {
                    "content": message["content"],
                    "melotts": message["data"]
                }

                voice_tmp_path = await self.my_tts.melotts_api(data)  
            elif message["tts_type"] == "none":
                # Audio.voice_tmp_path_queue.put(message)
                voice_tmp_path = None

            message["result"] = {
                "code": 200,
                "msg": "合成成功",
                "audio_path": voice_tmp_path
            }
        except Exception as e:
            logger.error(traceback.format_exc())
            message["result"] = {
                "code": -1,
                "msg": f"合成失败，{e}",
                "audio_path": None
            }

        return message

    # 发送音频播放信息给main内部的http服务端
    async def send_audio_play_info_to_callback(self, data: dict=None):
        """发送音频播放信息给main内部的http服务端

        Args:
            data (dict): 音频播放信息
        """
        try:
            if False == self.config.get("play_audio", "info_to_callback"):
                return None

            if data is None:
                data = {
                    "type": "audio_playback_completed",
                    "data": {
                        # 待播放音频数量
                        "wait_play_audio_num": len(Audio.voice_tmp_path_queue),
                        # 待合成音频的消息数量
                        "wait_synthesis_msg_num": len(Audio.message_queue),
                    }
                }

            logger.debug(f"data={data}")

            main_api_ip = "127.0.0.1" if self.config.get("api_ip") == "0.0.0.0" else self.config.get("api_ip")
            resp = await self.common.send_async_request(f'http://{main_api_ip}:{self.config.get("api_port")}/callback', "POST", data)

            return resp
        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 合成音频并插入待播放队列
    async def my_play_voice(self, message):
        """合成音频并插入待播放队列

        Args:
            message (dict): 待合成内容的json串

        Returns:
            bool: 合成情况
        """
        logger.debug(f"合成音频前的原始数据：{message['content']}")

        try:
            # 如果是tts类型为none，暂时这类为直接播放音频，所以就丢给路径队列
            if message["tts_type"] == "none":
                self.data_priority_insert("待播放音频列表", message)
                return
        except Exception as e:
            logger.error(traceback.format_exc())
            return

        try:
            logger.warning(f"合成音频前的原始数据：{message['content']}")
            message["content"] = self.common.remove_extra_words(message["content"], message["config"]["max_len"], message["config"]["max_char_len"])
            # logger.info("裁剪后的合成文本:" + text)

            message["content"] = message["content"].replace('\n', '。')

            # 空数据就散了吧
            if message["content"] == "":
                return
        except Exception as e:
            logger.error(traceback.format_exc())
            return
        

        # 判断消息类型，再变声并封装数据发到队列 减少冗余
        async def voice_change_and_put_to_queue(message, voice_tmp_path, content_copy):
            # 拼接json数据，存入队列
            data_json = {
                "type": message['type'],
                "voice_path": voice_tmp_path,
                "content": message["content"]
            }

            if "insert_index" in message:
                data_json["insert_index"] = message["insert_index"]

            # 区分消息类型是否是 回复xxx 并且 关闭了变声
            if message["type"] == "reply":
                # 是否开启了音频播放，如果没开，则不会传文件路径给播放队列
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("待播放音频列表", data_json)
                    return True
            # 区分消息类型是否是 念弹幕 并且 关闭了变声
            elif message["type"] == "read_comment" and not self.config.get("read_comment", "voice_change"):
                # 是否开启了音频播放，如果没开，则不会传文件路径给播放队列
                if self.config.get("play_audio", "enable"):
                    self.data_priority_insert("待播放音频列表", data_json)
                    return True

            voice_tmp_path = await self.voice_change(voice_tmp_path)
            
            # 更新音频路径
            data_json["voice_path"] = voice_tmp_path

            # 动作映射
            if self.config.get("action_mapping", "enable") and message['type'] in ["comment"]:
                logger.warning(data_json)
                # 将音频路径转换为音频url，如E:\GitHub_pro\AI-Vtuber\out\gpt_sovits_7.wav 转换为 http://127.0.0.1:8081/out/gpt_sovits_7.wav
                # 其中127.0.0.1:8081 是webui的ip和端口，从config中读取，如果ip为0.0.0.0，则表示为使用上网卡的ip做为url的ip
                audio_url = self.convert_path_to_url(voice_tmp_path)
                self.action_mapping_handle(content_copy, audio_url, voice_tmp_path)

            # 是否开启了音频播放，如果没开，则不会传文件路径给播放队列
            # 特殊处理，强制不播放音频 给unity播放
            if self.config.get("play_audio", "enable") and False:
                self.data_priority_insert("待播放音频列表", data_json)

            return True

        # 先对message["content"]进行正则匹配「」中提取的内容是要合成的文本,[]中提取的内容是要合成的动作
        pattern = r"「(.*?)」"
        matches = re.findall(pattern, message["content"])

        # 假设只关心第一个匹配到的内容作为要合成的文本
        if not matches or len(matches) == 0:
            return False
        content_copy = copy.copy(message["content"])
        message["content"] = matches[0]
        resp_json = await self.tts_handle(message)
        if resp_json["result"]["code"] == 200:
            voice_tmp_path = resp_json["result"]["audio_path"]
        else:
            voice_tmp_path = None
        
        if voice_tmp_path is None:
            logger.error(f"{message['tts_type']}合成失败，请排查服务端是否启动、是否正常，配置、网络等问题。如果排查后都没有问题，可能是接口改动导致的兼容性问题，可以前往官方仓库提交issue，传送门：https://github.com/Ikaros-521/AI-Vtuber/issues\n如果是GSV 400错误，请确认参考音频和参考文本是否正确，或替换参考音频进行尝试")
            self.abnormal_alarm_handle("tts")
            
            return False
        
        logger.info(f"[{message['tts_type']}]合成成功，合成内容：【{message['content']}】，音频存储在 {voice_tmp_path}")
        
        await voice_change_and_put_to_queue(message, voice_tmp_path, content_copy)  

        return True

    # 音频变速
    def audio_speed_change(self, audio_path, speed_factor=1.0, pitch_factor=1.0):
        """音频变速

        Args:
            audio_path (str): 音频路径
            speed (int, optional): 部分速度倍率.  默认 1.
            type (int, optional): 变调倍率 1为不变调.  默认 1.

        Returns:
            str: 变速后的音频路径
        """
        logger.debug(f"audio_path={audio_path}, speed_factor={speed_factor}, pitch_factor={pitch_factor}")

        # 使用 pydub 打开音频文件
        audio = AudioSegment.from_file(audio_path)

        # 变速
        if speed_factor > 1.0:
            audio_changed = audio.speedup(playback_speed=speed_factor)
        elif speed_factor < 1.0:
            # 如果要放慢,使用set_frame_rate调帧率
            orig_frame_rate = audio.frame_rate
            slow_frame_rate = int(orig_frame_rate * speed_factor)
            audio_changed = audio._spawn(audio.raw_data, overrides={"frame_rate": slow_frame_rate})
        else:
            audio_changed = audio

        # 变调
        if pitch_factor != 1.0:
            semitones = 12 * (pitch_factor - 1)
            audio_changed = audio_changed._spawn(audio_changed.raw_data, overrides={
                "frame_rate": int(audio_changed.frame_rate * (2.0 ** (semitones / 12.0)))
            }).set_frame_rate(audio_changed.frame_rate)

        # 变速
        # audio_changed = audio.speedup(playback_speed=speed_factor)

        # # 变调
        # if pitch_factor != 1.0:
        #     semitones = 12 * (pitch_factor - 1)
        #     audio_changed = audio_changed._spawn(audio_changed.raw_data, overrides={
        #         "frame_rate": int(audio_changed.frame_rate * (2.0 ** (semitones / 12.0)))
        #     }).set_frame_rate(audio_changed.frame_rate)

        # 导出为临时文件
        audio_out_path = self.config.get("play_audio", "out_path")
        if not os.path.isabs(audio_out_path):
            if not audio_out_path.startswith('./'):
                audio_out_path = './' + audio_out_path
        file_name = f"temp_{self.common.get_bj_time(4)}.wav"
        temp_path = self.common.get_new_audio_path(audio_out_path, file_name)

        # 导出为新音频文件
        audio_changed.export(temp_path, format="wav")

        # 转换为绝对路径
        temp_path = os.path.abspath(temp_path)

        return temp_path


    # 只进行普通音频播放   
    async def only_play_audio(self):
        try:
            captions_config = self.config.get("captions")

            try:
                if self.config.get("play_audio", "player") in ["pygame"]:
                    Audio.mixer_normal.init()
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("pygame mixer_normal初始化失败，普通音频将无法正常播放，请检查声卡是否正常！")

            while True:
                try:
                    # 获取线程锁，避免同时操作
                    with Audio.voice_tmp_path_queue_lock:
                        while not Audio.voice_tmp_path_queue:
                            # 消费者在消费完一个消息后，如果列表为空，则调用wait()方法阻塞自己，直到有新消息到来
                            Audio.voice_tmp_path_queue_not_empty.wait()  # 阻塞直到列表非空
                        data_json = Audio.voice_tmp_path_queue.pop(0)
                    
                    logger.debug(f"普通音频播放队列 即将播放音频 data_json={data_json}")

                    voice_tmp_path = data_json["voice_path"]

                    # 如果文案标志位为2，则说明在播放中，需要暂停
                    if Audio.copywriting_play_flag == 2:
                        logger.debug("暂停文案播放，等待一个切换间隔")
                        # 文案暂停
                        self.pause_copywriting_play()
                        Audio.copywriting_play_flag = 1
                        # 等待一个切换时间
                        await asyncio.sleep(float(self.config.get("copywriting", "switching_interval")))
                        logger.debug(f"切换间隔结束，准备播放普通音频")

                    # 是否启用字幕输出
                    if captions_config["enable"]:
                        # 输出当前播放的音频文件的文本内容到字幕文件中
                        self.common.write_content_to_file(captions_config["file_path"], data_json["content"], write_log=False)


                    # 判断是否发送web字幕打印机
                    if self.config.get("web_captions_printer", "enable"):
                        await self.common.send_to_web_captions_printer(self.config.get("web_captions_printer", "api_ip_port"), data_json)

                    # 洛曦 直播弹幕助手
                    if self.config.get("luoxi_project", "Live_Comment_Assistant", "enable") and \
                        "音频播放时" in self.config.get("luoxi_project", "Live_Comment_Assistant", "trigger_position"):
                        from utils.luoxi_project.live_comment_assistant import send_msg_to_live_comment_assistant

                        # 将音频消息类型type 转换为 判断用的新type
                        type_mapping = {
                            "comment": "comment_reply",
                            "idle_time_task": "idle_time_task",
                            "entrance": "entrance_reply",
                            "follow": "follow_reply",
                            "gift": "gift_reply",
                            "reread": "reread",
                            "schedule": "schedule",
                        }  

                        if data_json["type"] in type_mapping:
                            tmp_type = type_mapping[data_json["type"]]
                            # 当前消息类型是使能的触发类型
                            if tmp_type in self.config.get("luoxi_project", "Live_Comment_Assistant", "type"):
                                await send_msg_to_live_comment_assistant(self.config.get("luoxi_project", "Live_Comment_Assistant"), data_json["content"])


                    normal_interval_min = self.config.get("play_audio", "normal_interval_min")
                    normal_interval_max = self.config.get("play_audio", "normal_interval_max")
                    normal_interval = self.common.get_random_value(normal_interval_min, normal_interval_max)

                    interval_num_min = float(self.config.get("play_audio", "interval_num_min"))
                    interval_num_max = float(self.config.get("play_audio", "interval_num_max"))
                    interval_num = int(self.common.get_random_value(interval_num_min, interval_num_max))

                    for i in range(interval_num):
                        # 不仅仅是说话间隔，还是等待文本捕获刷新数据
                        await asyncio.sleep(normal_interval)

                    # 音频变速
                    random_speed = 1
                    if self.config.get("audio_random_speed", "normal", "enable"):
                        random_speed = self.common.get_random_value(self.config.get("audio_random_speed", "normal", "speed_min"),
                                                                    self.config.get("audio_random_speed", "normal", "speed_max"))
                        voice_tmp_path = self.audio_speed_change(voice_tmp_path, random_speed)

                    # print(voice_tmp_path)

                    # 根据接入的虚拟身体类型执行不同逻辑
                    if self.config.get("visual_body") == "xuniren":
                        await self.xuniren_api(voice_tmp_path)
                    elif self.config.get("visual_body") == "EasyAIVtuber":
                        await self.EasyAIVtuber_api(voice_tmp_path)
                    elif self.config.get("visual_body") == "digital_human_video_player":
                        await self.digital_human_video_player_api(voice_tmp_path)
                    elif self.config.get("visual_body") == "live2d_TTS_LLM_GPT_SoVITS_Vtuber":
                        await self.live2d_TTS_LLM_GPT_SoVITS_Vtuber_api(voice_tmp_path)
                    else:
                        # 根据播放器类型进行区分
                        if self.config.get("play_audio", "player") in ["audio_player", "audio_player_v2"]:
                            if "insert_index" in data_json:
                                data_json = {
                                    "type": data_json["type"],
                                    "voice_path": voice_tmp_path,
                                    "content": data_json["content"],
                                    "random_speed": {
                                        "enable": False,
                                        "max": 1.3,
                                        "min": 0.8
                                    },
                                    "speed": 1,
                                    "insert_index": data_json["insert_index"]
                                }
                            else:
                                data_json = {
                                    "type": data_json["type"],
                                    "voice_path": voice_tmp_path,
                                    "content": data_json["content"],
                                    "random_speed": {
                                        "enable": False,
                                        "max": 1.3,
                                        "min": 0.8
                                    },
                                    "speed": 1
                                }
                            Audio.audio_player.play(data_json)
                        else:
                            logger.debug(f"voice_tmp_path={voice_tmp_path}")
                            import pygame

                            try:
                                # 使用pygame播放音频
                                Audio.mixer_normal.music.load(voice_tmp_path)
                                Audio.mixer_normal.music.play()
                                while Audio.mixer_normal.music.get_busy():
                                    pygame.time.Clock().tick(10)
                                Audio.mixer_normal.music.stop()
                                
                                await self.send_audio_play_info_to_callback()
                            except pygame.error as e:
                                logger.error(traceback.format_exc())
                                # 如果发生 pygame.error 异常，则捕获并处理它
                                logger.error(f"无法加载音频文件:{voice_tmp_path}。请确保文件格式正确且文件未损坏。可能原因是TTS配置有误或者TTS服务端有问题，可以去服务端排查一下问题")

                    # 是否启用字幕输出
                    #if captions_config["enable"]:
                        # 清空字幕文件
                        # self.common.write_content_to_file(captions_config["file_path"], "")

                    if Audio.copywriting_play_flag == 1:
                        # 延时执行恢复文案播放
                        self.delayed_execution_unpause_copywriting_play()
                except Exception as e:
                    logger.error(traceback.format_exc())
            Audio.mixer_normal.quit()
        except Exception as e:
            logger.error(traceback.format_exc())


    # 停止当前播放的音频
    def stop_current_audio(self):
        if self.config.get("play_audio", "player") == "audio_player":
            Audio.audio_player.skip_current_stream()
        else:
            Audio.mixer_normal.music.fadeout(1000)

    """
                                                     ./@\]                    
                   ,@@@@\*                             \@@^ ,]]]              
                      [[[*                      /@@]@@@@@/[[\@@@@/            
                        ]]@@@@@@\              /@@^  @@@^]]`[[                
                ]]@@@@@@@[[*                   ,[`  /@@\@@@@@@@@@@@@@@^       
             [[[[[`   @@@/                 \@@@@[[[\@@^ =@@/                  
              .\@@\* *@@@`                           [\@@@@@@\`               
                 ,@@\=@@@                         ,]@@@/`  ,\@@@@*            
                   ,@@@@`                     ,[[[[`  =@@@   ]]/O             
                   /@@@@@`                    ]]]@@@@@@@@@/[[[[[`             
                ,@@@@[ \@@@\`                      ./@@@@@@@]                 
          ,]/@@@@/`      \@@@@@\]]               ,@@@/,@@^ \@@@\]             
                           ,@@@@@@@@/[*       ,/@@/*  /@@^   [@@@@@@@\*       
                                                      ,@@^                    
                                                              
    """
    # 延时执行恢复文案播放
    def delayed_execution_unpause_copywriting_play(self):
        # 如果已经有计时器在运行，则取消之前的计时器
        if Audio.unpause_copywriting_play_timer is not None and Audio.unpause_copywriting_play_timer.is_alive():
            Audio.unpause_copywriting_play_timer.cancel()

        # 创建新的计时器并启动
        Audio.unpause_copywriting_play_timer = threading.Timer(float(self.config.get("copywriting", "switching_interval")), 
                                                               self.unpause_copywriting_play)
        Audio.unpause_copywriting_play_timer.start()


    # 只进行文案播放 正经版
    def start_only_play_copywriting(self):
        logger.info(f"文案播放线程运行中...")
        asyncio.run(self.only_play_copywriting())


    # 只进行文案播放   
    async def only_play_copywriting(self):
        
        try:
            try:
                if self.config.get("play_audio", "player") in ["pygame"]:
                    Audio.mixer_copywriting.init()
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("pygame mixer_copywriting初始化失败，文案音频将无法正常播放，请检查声卡是否正常！")

            async def random_speed_and_play(audio_path):
                """对音频进行变速和播放，内置延时，其实就是提取了公共部分

                Args:
                    audio_path (str): 音频路径
                """
                # 音频变速
                random_speed = 1
                if self.config.get("audio_random_speed", "copywriting", "enable"):
                    random_speed = self.common.get_random_value(self.config.get("audio_random_speed", "copywriting", "speed_min"),
                                                                self.config.get("audio_random_speed", "copywriting", "speed_max"))
                    audio_path = self.audio_speed_change(audio_path, random_speed)

                logger.info(f"变速后音频输出在 {audio_path}")

                # 根据接入的虚拟身体类型执行不同逻辑
                if self.config.get("visual_body") == "xuniren":
                    await self.xuniren_api(audio_path)
                else:
                    if self.config.get("play_audio", "player") in ["audio_player", "audio_player_v2"]:
                            data_json = {
                                "type": "copywriting",
                                "voice_path": audio_path,
                                "content": audio_path,
                                "random_speed": {
                                    "enable": False,
                                    "max": 1.3,
                                    "min": 0.8
                                },
                                "speed": 1
                            }
                            Audio.audio_player.play(data_json)
                    else:
                        import pygame

                        try:
                            # 使用pygame播放音频
                            Audio.mixer_copywriting.music.load(audio_path)
                            Audio.mixer_copywriting.music.play()
                            while Audio.mixer_copywriting.music.get_busy():
                                pygame.time.Clock().tick(10)
                            Audio.mixer_copywriting.music.stop()

                            await self.send_audio_play_info_to_callback()
                        except pygame.error as e:
                            logger.error(traceback.format_exc())
                            # 如果发生 pygame.error 异常，则捕获并处理它
                            logger.error(f"无法加载音频文件:{voice_tmp_path}。请确保文件格式正确且文件未损坏。可能原因是TTS配置有误或者TTS服务端有问题，可以去服务端排查一下问题")


                # 添加延时，暂停执行n秒钟
                await asyncio.sleep(float(self.config.get("copywriting", "audio_interval")))


            def reload_tmp_play_list(index, play_list_arr):
                """重载播放列表

                Args:
                    index (int): 文案索引
                """
                # 获取文案配置
                copywriting_configs = self.config.get("copywriting", "config")
                tmp_play_list = copy.copy(copywriting_configs[index]["play_list"])
                play_list_arr[index] = tmp_play_list

                # 是否开启随机列表播放
                if self.config.get("copywriting", "random_play"):
                    for play_list in play_list_arr:
                        # 随机打乱列表内容
                        random.shuffle(play_list)


            try:
                # 获取文案配置
                copywriting_configs = self.config.get("copywriting", "config")

                # 获取自动播放配置
                if self.config.get("copywriting", "auto_play"):
                    self.unpause_copywriting_play()

                file_path_arr = []
                audio_path_arr = []
                play_list_arr = []
                continuous_play_num_arr = []
                max_play_time_arr = []
                # 记录最后一次播放的音频列表的索引值
                last_index = -1

                # 重载所有数据
                def all_data_reload(file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr):      
                    logger.info("重载所有文案数据")

                    file_path_arr = []
                    audio_path_arr = []
                    play_list_arr = []
                    continuous_play_num_arr = []
                    max_play_time_arr = []
                    
                    # 遍历文案配置载入数组
                    for copywriting_config in copywriting_configs:
                        file_path_arr.append(copywriting_config["file_path"])
                        audio_path_arr.append(copywriting_config["audio_path"])
                        tmp_play_list = copy.copy(copywriting_config["play_list"])
                        play_list_arr.append(tmp_play_list)
                        continuous_play_num_arr.append(copywriting_config["continuous_play_num"])
                        max_play_time_arr.append(copywriting_config["max_play_time"])


                    # 是否开启随机列表播放
                    if self.config.get("copywriting", "random_play"):
                        for play_list in play_list_arr:
                            # 随机打乱列表内容
                            random.shuffle(play_list)

                    return file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr

                file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr = all_data_reload(file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr)

                while True:
                    # print(f"Audio.copywriting_play_flag={Audio.copywriting_play_flag}")

                    # 判断播放标志位
                    if Audio.copywriting_play_flag in [0, 1, -1]:
                        await asyncio.sleep(float(self.config.get("copywriting", "audio_interval")))  # 添加延迟减少循环频率
                        continue

                    # print(f"play_list_arr={play_list_arr}")

                    # 遍历 play_list_arr 中的每个 play_list
                    for index, play_list in enumerate(play_list_arr):
                        # print(f"play_list_arr={play_list_arr}")

                        # 判断播放标志位 防止播放过程中无法暂停
                        if Audio.copywriting_play_flag in [0, 1, -1]:
                            # print(f"Audio.copywriting_play_flag={Audio.copywriting_play_flag}")
                            file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr = all_data_reload(file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr)

                            break

                        # 判断当前播放列表的索引值是否小于上一次的索引值，小的话就下一个，用于恢复到被打断前的播放位置
                        if index < last_index:
                            continue

                        start_time = float(self.common.get_bj_time(3))

                        # 根据连续播放的文案数量进行循环
                        for i in range(0, continuous_play_num_arr[index]):
                            # print(f"continuous_play_num_arr[index]={continuous_play_num_arr[index]}")
                            # 判断播放标志位 防止播放过程中无法暂停
                            if Audio.copywriting_play_flag in [0, 1, -1]:
                                file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr = all_data_reload(file_path_arr, audio_path_arr, play_list_arr, continuous_play_num_arr, max_play_time_arr)

                                break
                            
                            # 判断当前时间是否已经超过限定的播放时间，超时则退出循环
                            if (float(self.common.get_bj_time(3)) - start_time) > max_play_time_arr[index]:
                                break

                            # 判断当前 play_list 是否有音频数据
                            if len(play_list) > 0:
                                # 移出一个音频路径
                                voice_tmp_path = play_list.pop(0)
                                audio_path = os.path.join(audio_path_arr[index], voice_tmp_path)
                                audio_path = os.path.abspath(audio_path)
                                logger.info(f"即将播放音频 {audio_path}")

                                await random_speed_and_play(audio_path)
                            else:
                                # 重载播放列表
                                reload_tmp_play_list(index, play_list_arr)

                        # 放在这一级别，只有这一索引的播放列表的音频播放完后才会记录最后一次的播放索引位置
                        last_index = index if index < (len(play_list_arr) - 1) else -1
            except Exception as e:
                logger.error(traceback.format_exc())
            
            if self.config.get("play_audio", "player") in ["pygame"]:
                Audio.mixer_copywriting.quit()
        except Exception as e:
            logger.error(traceback.format_exc())


    # 暂停文案播放
    def pause_copywriting_play(self):
        logger.info("暂停文案播放")
        Audio.copywriting_play_flag = 0
        if self.config.get("play_audio", "player") == "audio_player":
            pass
            Audio.audio_player.pause_stream()
        # 由于v2的暂停不会更换音频，所以这个只暂停文案就没有意义了
        elif self.config.get("play_audio", "player") == "audio_player_v2":
            pass
            # Audio.audio_player.pause_stream()
        else:
            Audio.mixer_copywriting.music.pause()

    
    # 恢复暂停文案播放
    def unpause_copywriting_play(self):
        logger.info("恢复文案播放")
        Audio.copywriting_play_flag = 2
        # print(f"Audio.copywriting_play_flag={Audio.copywriting_play_flag}")
        if self.config.get("play_audio", "player") in ["audio_player", "audio_player_v2"]:
            pass
            Audio.audio_player.resume_stream()
        else:
            Audio.mixer_copywriting.music.unpause()

    
    # 停止文案播放
    def stop_copywriting_play(self):
        logger.info("停止文案播放")
        Audio.copywriting_play_flag = 0
        if self.config.get("play_audio", "player") == "audio_player":
            Audio.audio_player.pause_stream()
        # 由于v2的暂停不会更换音频，所以这个只暂停文案就没有意义了
        elif self.config.get("play_audio", "player") == "audio_player_v2":
            pass
            # Audio.audio_player.pause_stream()
        else:
            Audio.mixer_copywriting.music.stop()


    # 合并文案音频文件
    def merge_audio_files(self, directory, base_filename, last_index, pause_duration=1, format="wav"):
        merged_audio = None

        for i in range(1, last_index+1):
            filename = f"{base_filename}-{i}.{format}"  # 假设音频文件为 wav 格式
            filepath = os.path.join(directory, filename)

            if os.path.isfile(filepath):
                audio_segment = AudioSegment.from_file(filepath)
                
                if pause_duration > 0 and merged_audio is not None:
                    pause = AudioSegment.silent(duration=pause_duration * 1000)  # 将秒数转换为毫秒
                    merged_audio += pause
                
                if merged_audio is None:
                    merged_audio = audio_segment
                else:
                    merged_audio += audio_segment

                os.remove(filepath)  # 删除已合并的音频文件

        if merged_audio is not None:
            merged_filename = f"{base_filename}.wav"  # 合并后的文件名
            merged_filepath = os.path.join(directory, merged_filename)
            merged_audio.export(merged_filepath, format="wav")
            logger.info(f"音频文件合并成功：{merged_filepath}")
        else:
            logger.error("没有找到要合并的音频文件")


    # 使用本地配置进行音频合成，返回音频路径
    async def audio_synthesis_use_local_config(self, content, audio_synthesis_type="edge-tts"):
        """使用本地配置进行音频合成，返回音频路径

        Args:
            content (str): 待合成的文本内容
            audio_synthesis_type (str, optional): 使用的tts类型. Defaults to "edge-tts".

        Returns:
            str: 合成的音频的路径
        """
        # 重载配置
        self.reload_config(self.config_path)

        vits = self.config.get("vits")
        vits_fast = self.config.get("vits_fast")
        bark_gui = self.config.get("bark_gui")
        vall_e_x = self.config.get("vall_e_x")
        openai_tts = self.config.get("openai_tts")
    
        if audio_synthesis_type == "vits":
            # 语言检测
            language = self.common.lang_check(content)

            # logger.info("language=" + language)

            data = {
                "type": vits["type"],
                "api_ip_port": vits["api_ip_port"],
                "id": vits["id"],
                "format": vits["format"],
                "lang": language,
                "length": vits["length"],
                "noise": vits["noise"],
                "noisew": vits["noisew"],
                "max": vits["max"],
                "sdp_radio": vits["sdp_radio"],
                "content": content,
                "gpt_sovits": vits["gpt_sovits"],
            }

            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.vits_api(data)
                

        elif audio_synthesis_type == "bert_vits2":
        
            if self.config.get("bert_vits2", "language") == "auto":
                # 自动检测语言
                language = self.common.lang_check(content)

                logger.debug(f'language={language}')

                # 自定义语言名称（需要匹配请求解析）
                language_name_dict = {"en": "EN", "zh": "ZH", "ja": "JP"}  

                if language in language_name_dict:
                    language = language_name_dict[language]
                else:
                    language = "ZH"  # 无法识别出语言代码时的默认值
            else:
                language = self.config.get("bert_vits2", "language")
                
            data = {
                "api_ip_port": self.config.get("bert_vits2", "api_ip_port"),
                "type": self.config.get("bert_vits2", "type"),
                "model_id": self.config.get("bert_vits2", "model_id"),
                "speaker_name": self.config.get("bert_vits2", "speaker_name"),
                "speaker_id": self.config.get("bert_vits2", "speaker_id"),
                "language": language,
                "length": self.config.get("bert_vits2", "length"),
                "noise": self.config.get("bert_vits2", "noise"),
                "noisew": self.config.get("bert_vits2", "noisew"),
                "sdp_radio": self.config.get("bert_vits2", "sdp_radio"),
                "auto_translate": self.config.get("bert_vits2", "auto_translate"),
                "auto_split": self.config.get("bert_vits2", "auto_split"),
                "emotion": self.config.get("bert_vits2", "emotion"),
                "style_text": self.config.get("bert_vits2", "style_text"),
                "style_weight": self.config.get("bert_vits2", "style_weight"),
                "刘悦-中文特化API": self.config.get("bert_vits2", "刘悦-中文特化API"),
                "content": content
            }

            logger.info(f"data={data}")

            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.bert_vits2_api(data)
        elif audio_synthesis_type == "vits_fast":
            if vits_fast["language"] == "自动识别":
                # 自动检测语言
                language = self.common.lang_check(content)

                logger.debug(f'language={language}')

                # 自定义语言名称（需要匹配请求解析）
                language_name_dict = {"en": "English", "zh": "简体中文", "ja": "日本語"}  

                if language in language_name_dict:
                    language = language_name_dict[language]
                else:
                    language = "简体中文"  # 无法识别出语言代码时的默认值
            else:
                language = vits_fast["language"]

            # logger.info("language=" + language)

            data = {
                "api_ip_port": vits_fast["api_ip_port"],
                "character": vits_fast["character"],
                "speed": vits_fast["speed"],
                "language": language,
                "content": content
            }

            # 调用接口合成语音
            voice_tmp_path = self.my_tts.vits_fast_api(data)
        elif audio_synthesis_type == "edge-tts":
            data = {
                "content": content,
                "edge-tts": self.config.get("edge-tts")
            }

            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.edge_tts_api(data)

        elif audio_synthesis_type == "elevenlabs":
            return None
        
            try:
                # 如果配置了密钥就设置上0.0
                if message["data"]["elevenlabs_api_key"] != "":
                    set_api_key(message["data"]["elevenlabs_api_key"])

                audio = generate(
                    text=message["content"],
                    voice=message["data"]["elevenlabs_voice"],
                    model=message["data"]["elevenlabs_model"]
                )

                # play(audio)
            except Exception as e:
                logger.error(traceback.format_exc())
                return
        elif audio_synthesis_type == "bark_gui":
            data = {
                "api_ip_port": bark_gui["api_ip_port"],
                "spk": bark_gui["spk"],
                "generation_temperature": bark_gui["generation_temperature"],
                "waveform_temperature": bark_gui["waveform_temperature"],
                "end_of_sentence_probability": bark_gui["end_of_sentence_probability"],
                "quick_generation": bark_gui["quick_generation"],
                "seed": bark_gui["seed"],
                "batch_count": bark_gui["batch_count"],
                "content": content
            }

            # 调用接口合成语音
            voice_tmp_path = self.my_tts.bark_gui_api(data)
        elif audio_synthesis_type == "vall_e_x":
            data = {
                "api_ip_port": vall_e_x["api_ip_port"],
                "language": vall_e_x["language"],
                "accent": vall_e_x["accent"],
                "voice_preset": vall_e_x["voice_preset"],
                "voice_preset_file_path":vall_e_x["voice_preset_file_path"],
                "content": content
            }

            # 调用接口合成语音
            voice_tmp_path = self.my_tts.vall_e_x_api(data)
        elif audio_synthesis_type == "genshinvoice_top":
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.genshinvoice_top_api(content)

        elif audio_synthesis_type == "tts_ai_lab_top":
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.tts_ai_lab_top_api(content)

        elif audio_synthesis_type == "openai_tts":
            data = {
                "type": openai_tts["type"],
                "api_ip_port": openai_tts["api_ip_port"],
                "model": openai_tts["model"],
                "voice": openai_tts["voice"],
                "api_key": openai_tts["api_key"],
                "content": content
            }

            # 调用接口合成语音
            voice_tmp_path = self.my_tts.openai_tts_api(data)
            
        elif audio_synthesis_type == "reecho_ai":
            data = content
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.reecho_ai_api(data)

        elif audio_synthesis_type == "gradio_tts":
            data = {
                "request_parameters": self.config.get("gradio_tts", "request_parameters"),
                "content": content
            }
            # 调用接口合成语音
            voice_tmp_path = self.my_tts.gradio_tts_api(data)
        elif audio_synthesis_type == "gpt_sovits":
            if self.config.get("gpt_sovits", "language") == "自动识别":
                # 自动检测语言
                language = self.common.lang_check(content)

                logger.debug(f'language={language}')

                # 自定义语言名称（需要匹配请求解析）
                language_name_dict = {"en": "英文", "zh": "中文", "ja": "日文"}  

                if language in language_name_dict:
                    language = language_name_dict[language]
                else:
                    language = "中文"  # 无法识别出语言代码时的默认值
            else:
                language = self.config.get("gpt_sovits", "language")

            # 传太多有点冗余了
            data = {
                "type": self.config.get("gpt_sovits", "type"),
                "gradio_ip_port": self.config.get("gpt_sovits", "gradio_ip_port"),
                "ws_ip_port": self.config.get("gpt_sovits", "ws_ip_port"),
                "api_ip_port": self.config.get("gpt_sovits", "api_ip_port"),
                "ref_audio_path": self.config.get("gpt_sovits", "ref_audio_path"),
                "prompt_text": self.config.get("gpt_sovits", "prompt_text"),
                "prompt_language": self.config.get("gpt_sovits", "prompt_language"),
                "language": language,
                "cut": self.config.get("gpt_sovits", "cut"),
                "api_0322": self.config.get("gpt_sovits", "api_0322"),
                "api_0706": self.config.get("gpt_sovits", "api_0706"),
                "v2_api_0821": self.config.get("gpt_sovits", "v2_api_0821"),
                "webtts": self.config.get("gpt_sovits", "webtts"),
                "content": content
            }
                    
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.gpt_sovits_api(data)
        
        elif audio_synthesis_type == "clone_voice":
            data = {
                "type": self.config.get("clone_voice", "type"),
                "api_ip_port": self.config.get("clone_voice", "api_ip_port"),
                "voice": self.config.get("clone_voice", "voice"),
                "language": self.config.get("clone_voice", "language"),
                "speed": self.config.get("clone_voice", "speed"),
                "content": content
            }
                    
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.clone_voice_api(data)

        elif audio_synthesis_type == "azure_tts":
            data = {
                "subscription_key": self.config.get("azure_tts", "subscription_key"),
                "region": self.config.get("azure_tts", "region"),
                "voice_name": self.config.get("azure_tts", "voice_name"),
                "content": content
            }

            logger.debug(f"data={data}")

            voice_tmp_path = self.my_tts.azure_tts_api(data) 
        elif audio_synthesis_type == "fish_speech":
            data = self.config.get("fish_speech")

            if data["type"] == "web":
                data["web"]["content"] = content
                logger.debug(f"data={data}")
                voice_tmp_path = await self.my_tts.fish_speech_web_api(data["web"])
            else:
                data["tts_config"]["text"] = content
                data["api_1.1.0"]["text"] = content
                logger.debug(f"data={data}")
                voice_tmp_path = await self.my_tts.fish_speech_api(data)
        elif audio_synthesis_type == "chattts":
            data = {
                "type": self.config.get("chattts", "type"),
                "api_ip_port": self.config.get("chattts", "api_ip_port"),
                "gradio_ip_port": self.config.get("chattts", "gradio_ip_port"),
                "temperature": self.config.get("chattts", "temperature"),
                "audio_seed_input": self.config.get("chattts", "audio_seed_input"),
                "top_p": self.config.get("chattts", "top_p"),
                "top_k": self.config.get("chattts", "top_k"),
                "text_seed_input": self.config.get("chattts", "text_seed_input"),
                "refine_text_flag": self.config.get("chattts", "refine_text_flag"),
                "api": self.config.get("chattts", "api"),
                "content": content
            }
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.chattts_api(data)
        elif audio_synthesis_type == "cosyvoice":
            data = {
                "type": self.config.get("cosyvoice", "type"),
                "gradio_ip_port": self.config.get("cosyvoice", "gradio_ip_port"),
                "api_ip_port": self.config.get("cosyvoice", "api_ip_port"),
                "gradio_0707": self.config.get("cosyvoice", "gradio_0707"),
                "api_0819": self.config.get("cosyvoice", "api_0819"),
                "api": self.config.get("cosyvoice", "api"),
                "content": content
            }
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.cosyvoice_api(data)
        elif audio_synthesis_type == "f5_tts":
            data = {
                "type": self.config.get("f5_tts", "type"),
                "gradio_ip_port": self.config.get("f5_tts", "gradio_ip_port"),
                "ref_audio_orig": self.config.get("f5_tts", "ref_audio_orig"),
                "ref_text": self.config.get("f5_tts", "ref_text"),
                "model": self.config.get("f5_tts", "model"),
                "remove_silence": self.config.get("f5_tts", "remove_silence"),
                "cross_fade_duration": self.config.get("f5_tts", "cross_fade_duration"),
                "speed": self.config.get("f5_tts", "speed"),
                "content": content
            }
            # 调用接口合成语音
            voice_tmp_path = await self.my_tts.f5_tts_api(data)
        elif audio_synthesis_type == "multitts":
            data = {
                "content": content,
                "multitts": self.config.get(audio_synthesis_type),
            }
            voice_tmp_path = await self.my_tts.multitts_api(data)
        elif audio_synthesis_type == "melotts":
            data = {
                "content": content,
                "melotts": self.config.get(audio_synthesis_type),
            }
            voice_tmp_path = await self.my_tts.melotts_api(data)

        return voice_tmp_path


    # 只进行文案音频合成
    async def copywriting_synthesis_audio(self, file_path, out_audio_path="out/", audio_synthesis_type="edge-tts"):
        """文案音频合成

        Args:
            file_path (str): 文案文本文件路径
            out_audio_path (str, optional): 音频输出的文件夹路径. Defaults to "out/".
            audio_synthesis_type (str, optional): 语音合成类型. Defaults to "edge-tts".

        Raises:
            Exception: _description_
            Exception: _description_

        Returns:
            str: 合成完毕的音频路径
        """
        try:
            max_len = self.config.get("filter", "max_len")
            max_char_len = self.config.get("filter", "max_char_len")
            file_path = os.path.join(file_path)

            audio_out_path = self.config.get("play_audio", "out_path")

            if not os.path.isabs(audio_out_path):
                if audio_out_path.startswith('./'):
                    audio_out_path = audio_out_path[2:]

                audio_out_path = os.path.join(os.getcwd(), audio_out_path)
                # 确保路径最后有斜杠
                if not audio_out_path.endswith(os.path.sep):
                    audio_out_path += os.path.sep


            logger.info(f"即将合成的文案：{file_path}")
            
            # 从文件路径提取文件名
            file_name = self.common.extract_filename(file_path)
            # 获取文件内容
            content = self.common.read_file_return_content(file_path)

            logger.debug(f"合成音频前的原始数据：{content}")
            content = self.common.remove_extra_words(content, max_len, max_char_len)
            # logger.info("裁剪后的合成文本:" + text)

            content = content.replace('\n', '。')

            # 变声并移动音频文件 减少冗余
            async def voice_change_and_put_to_queue(voice_tmp_path):
                voice_tmp_path = await self.voice_change(voice_tmp_path)

                if voice_tmp_path:
                    # 移动音频到 临时音频路径 并重命名
                    out_file_path = audio_out_path # os.path.join(os.getcwd(), audio_out_path)
                    logger.info(f"移动临时音频到 {out_file_path}")
                    self.common.move_file(voice_tmp_path, out_file_path, file_name + "-" + str(file_index))
                
                return voice_tmp_path

            # 文件名自增值，在后期多合一的时候起到排序作用
            file_index = 0

            # 是否语句切分
            if self.config.get("play_audio", "text_split_enable"):
                sentences = self.common.split_sentences(content)
            else:
                sentences = [content]

            logger.info(f"sentences={sentences}")
            
            # 遍历逐一合成文案音频
            for content in sentences:
                # 使用正则表达式替换头部的标点符号
                # ^ 表示字符串开始，[^\w\s] 匹配任何非字母数字或空白字符
                content = re.sub(r'^[^\w\s]+', '', content)

                # 设置重试次数
                retry_count = 3  
                while retry_count > 0:
                    file_index = file_index + 1

                    try:
                        voice_tmp_path = await self.audio_synthesis_use_local_config(content, audio_synthesis_type)
                        
                        if voice_tmp_path is None:
                            raise Exception(f"{audio_synthesis_type}合成失败")
                        
                        logger.info(f"{audio_synthesis_type}合成成功，合成内容：【{content}】，输出到={voice_tmp_path}") 

                        # 变声并移动音频文件 减少冗余
                        tmp_path = await voice_change_and_put_to_queue(voice_tmp_path)
                        if tmp_path is None:
                            raise Exception(f"{audio_synthesis_type}合成失败")

                        break
                    
                    except Exception as e:
                        logger.error(f"尝试失败，剩余重试次数：{retry_count - 1}")
                        logger.error(traceback.format_exc())
                        retry_count -= 1  # 减少重试次数
                        if retry_count <= 0:
                            logger.error(f"重试次数用尽，{audio_synthesis_type}合成最终失败，请排查配置、网络等问题")
                            self.abnormal_alarm_handle("tts")
                            return

            # 进行音频合并 输出到文案音频路径
            out_file_path = os.path.join(os.getcwd(), audio_out_path)
            self.merge_audio_files(out_file_path, file_name, file_index)

            file_path = os.path.join(os.getcwd(), audio_out_path, file_name + ".wav")
            logger.info(f"合成完毕后的音频位于 {file_path}")
            # 移动音频到 指定的文案音频路径 out_audio_path
            out_file_path = os.path.join(os.getcwd(), out_audio_path)
            logger.info(f"移动音频到 {out_file_path}")
            self.common.move_file(file_path, out_file_path)
            file_path = os.path.join(out_audio_path, file_name + ".wav")

            return file_path
        except Exception as e:
            logger.error(traceback.format_exc())
            return None
        

    """
    其他
    """
    
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
            Audio.abnormal_alarm_data[type]["error_count"] += 1

            if not self.config.get("abnormal_alarm", type, "enable"):
                return True

            logger.debug(f"abnormal_alarm_handle type={type}, error_count={Audio.abnormal_alarm_data[type]['error_count']}")

            if self.config.get("abnormal_alarm", type, "type") == "local_audio":
                # 是否错误数大于 自动重启错误数
                if Audio.abnormal_alarm_data[type]["error_count"] >= self.config.get("abnormal_alarm", type, "auto_restart_error_num"):
                    logger.warning(f"【异常报警-{type}】 出错数超过自动重启错误数，即将自动重启")
                    data = {
                        "type": "restart",
                        "api_type": "api",
                        "data": {
                            "config_path": "config.json"
                        }
                    }

                    webui_ip = "127.0.0.1" if self.config.get("webui", "ip") == "0.0.0.0" else self.config.get("webui", "ip")
                    self.common.send_request(f'http://{webui_ip}:{self.config.get("webui", "port")}/sys_cmd', "POST", data)
                    
                # 是否错误数小于 开始报警错误数，是则不触发报警
                if Audio.abnormal_alarm_data[type]["error_count"] < self.config.get("abnormal_alarm", type, "start_alarm_error_num"):
                    return
                
                path_list = self.common.get_all_file_paths(self.config.get("abnormal_alarm", type, "local_audio_path"))

                # 随机选择列表中的一个元素
                audio_path = random.choice(path_list)

                data_json = {
                    "type": "abnormal_alarm",
                    "tts_type": self.config.get("audio_synthesis_type"),
                    "data": self.config.get(self.config.get("audio_synthesis_type")),
                    "config": self.config.get("filter"),
                    "username": "系统",
                    "content": os.path.join(self.config.get("abnormal_alarm", type, "local_audio_path"), self.common.extract_filename(audio_path, True))
                }

                logger.warning(f"【异常报警-{type}】 {self.common.extract_filename(audio_path, False)}")

                self.audio_synthesis(data_json)

        except Exception as e:
            logger.error(traceback.format_exc())

            return False

        return True

    # 动作映射处理
    def action_mapping_handle(self, llm_content: str, audio_url: str, audio_path: str):
        """
        根据LLM生成内容匹配并判定对应的动作
        
        参数:
            llm_content: LLM生成的内容文本
            audio_url: 音频文件url
            audio_path: 音频文件路径
            
        返回:
            dict: 包含匹配结果的字典，格式如下:
                {
                    "action_name": 匹配到的动作名称,
                    "group_id": 匹配到的动作组,
                    "match_word": 匹配到的关键词,
                    "priority": 匹配优先级,
                    "timestamp": 匹配时间戳,
                    "id": 动作ID,
                    "duration": 音频时长（秒）
                }
                如果没有匹配到任何动作，则返回None
        """
        try:
            # 获取音频时长
            audio_duration = 0
            if audio_path and os.path.exists(audio_path):
                try:
                    # 尝试使用ffmpeg获取音频时长（通过ffprobe）
                    import subprocess
                    import json
                    
                    result = subprocess.run([
                        "ffprobe", 
                        "-v", "error", 
                        "-show_entries", "format=duration", 
                        "-of", "json", 
                        audio_path
                    ], capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        audio_duration = float(data['format']['duration'])
                        logger.info(f"使用ffprobe获取到音频文件时长: {audio_duration}秒")
                except Exception as e:
                    logger.error(f"使用ffprobe获取音频时长失败: {e}")
                    try:
                        # 尝试使用librosa获取音频时长（跨平台但较慢）
                        import librosa
                        y, sr = librosa.load(audio_path, sr=None)
                        audio_duration = librosa.get_duration(y=y, sr=sr)
                        logger.info(f"使用librosa获取到音频文件时长: {audio_duration}秒")
                    except Exception as e2:
                        logger.error(f"使用librosa获取音频时长失败: {e2}")
                        try:
                            # 尝试使用pygame获取音频时长
                            import pygame
                            pygame.mixer.init()
                            sound = pygame.mixer.Sound(audio_path)
                            audio_duration = sound.get_length()
                            logger.info(f"使用pygame获取到音频文件时长: {audio_duration}秒")
                            # 释放资源
                            del sound
                            pygame.mixer.quit()
                        except Exception as e3:
                            logger.error(f"使用pygame获取音频时长失败: {e3}")
                            try:
                                # 尝试使用wave模块（仅支持wav格式）
                                if audio_path.lower().endswith('.wav'):
                                    import wave
                                    with wave.open(audio_path, 'rb') as wf:
                                        # 获取帧率和帧数
                                        frames = wf.getnframes()
                                        rate = wf.getframerate()
                                        audio_duration = frames / float(rate)
                                        logger.info(f"使用wave模块获取到音频文件时长: {audio_duration}秒")
                            except Exception as e4:
                                logger.error(f"所有获取音频时长的方法都失败: {e4}")
            else:
                logger.warning(f"音频文件不存在或路径无效: {audio_path}")
            
            if not llm_content:
                return None
                
            # 获取配置
            action_config = self.config.get("action_mapping")
            if not action_config:
                return None
                
            # 根据llm_content进行动作映射
            group_ids = action_config.get("groups", [])
            if not group_ids:
                logger.info("动作映射配置中没有定义动作组")
                return None
                
            logger.info(f"开始匹配文本: {llm_content}")
            
            # 初始化变量
            matched_actions = []  # 存储所有匹配结果
            
            # 先检查是否有[]包围的动作名称
            import re
            name_matches = re.findall(r'\[(.*?)\]', llm_content)
            logger.info(f"从[]中提取的可能动作名称: {name_matches}")
            
            # 如果找到[]中的内容，尝试匹配动作名称
            if name_matches:
                for name_match in name_matches:
                    # 遍历所有动作组查找匹配
                    for group in group_ids:
                        group_id = group.get("id")
                        actions = group.get("actions", [])
                        
                        for action in actions:
                            action_name = action.get("name", "")
                            priority = action.get("priority", 0)
                            
                            # 检查是否精确匹配动作名称
                            if action_name and action_name == name_match:
                                logger.info(f"在[]中找到精确匹配动作名称: {action_name}")
                                # 找到精确匹配，直接返回结果
                                matched_result = {
                                    "action_name": action_name,
                                    "group_id": group_id,
                                    "match_word": action_name,
                                    "priority": priority,
                                    "audio_url": audio_url,
                                    "content": llm_content,
                                    "duration": audio_duration
                                }
                                
                                # 添加时间戳并存入队列
                                # 原始代码
                                # import time
                                # matched_result["timestamp"] = int(time.time())
                                # matched_result["id"] = len(Audio.action_mapping_queue) + 1
                                
                                # 添加到队列中
                                # Audio.action_mapping_queue.append(matched_result)
                                
                                # 如果队列超出最大长度，删除最早的记录
                                # if len(Audio.action_mapping_queue) > Audio.action_mapping_queue_max_size:
                                #     Audio.action_mapping_queue.pop(0)
                                
                                # 重置未匹配计数
                                Audio.no_match_count = 0

                                # 使用UnityQueueHandler添加动作映射
                                from main import unity_queue_handler
                                unity_queue_handler.add_action_mapping(matched_result)
                                return matched_result
            
            # 如果没有在[]中找到匹配的动作名称，则尝试从全文匹配关键词
            logger.info("在[]中未找到精确匹配，尝试匹配关键词")
            
            # 遍历所有动作组
            for group in group_ids:
                group_id = group.get("id")
                actions = group.get("actions", [])
                
                # logger.info(f"检查动作组 {group_id}, 包含 {len(actions)} 个动作")
                
                for action in actions:
                    action_name = action.get("name", "")
                    match_words = action.get("match_words", [])
                    priority = action.get("priority", 0)
                    
                    # 检查是否匹配关键词
                    for word in match_words:
                        # 英文匹配不区分大小写
                        if word.isascii():
                            if word.lower() in llm_content.lower():
                                logger.info(f"匹配到英文关键词: {word}")
                                matched_actions.append({
                                    "action_name": action_name,
                                    "group_id": group_id,
                                    "match_word": word,
                                    "priority": priority,
                                    "audio_url": audio_url,
                                    "content": llm_content,
                                    "duration": audio_duration
                                })
                        else:
                            if word in llm_content:
                                logger.info(f"匹配到中文关键词: {word}")
                                matched_actions.append({
                                    "action_name": action_name,
                                    "group_id": group_id,
                                    "match_word": word,
                                    "priority": priority,
                                    "audio_url": audio_url,
                                    "content": llm_content,
                                    "duration": audio_duration
                                })
            
            # 匹配结果
            matched_result = None
            
            # 处理关键词匹配的情况
            if matched_actions:
                # 按照优先级从高到低排序
                matched_actions.sort(key=lambda x: x["priority"], reverse=True)
                
                # 获取最高优先级
                highest_priority = matched_actions[0]["priority"]
                logger.info(f"最高匹配优先级: {highest_priority}")
                
                # 筛选出最高优先级的动作
                highest_priority_actions = [a for a in matched_actions if a["priority"] == highest_priority]
                
                # 同优先级随机选一个
                import random
                selected_action = random.choice(highest_priority_actions)
                logger.info(f"从{len(highest_priority_actions)}个同优先级动作中随机选择: {selected_action['action_name']}")
                
                matched_result = selected_action
            
            # 若未匹配到任何动作，检查是否需要强制匹配动作组1
            if not matched_result:
                Audio.no_match_count += 1
                logger.info(f"未匹配到任何动作，连续未匹配计数: {Audio.no_match_count}")
                
                if Audio.no_match_count >= 1:
                    # 连续三次未匹配，强制匹配动作组1
                    Audio.no_match_count = 0
                    
                    # 从动作组1中随机选择一个动作
                    group_1_actions = []
                    for group in group_ids:
                        if group.get("id") == 1:
                            group_1_actions = group.get("actions", [])
                            break
                    
                    if group_1_actions:
                        import random
                        selected_action = random.choice(group_1_actions)
                        matched_result = {
                            "action_name": selected_action.get("name", ""),
                            "group_id": 1,
                            "match_word": "强制匹配",
                            "priority": selected_action.get("priority", 0),
                            "audio_url": audio_url,
                            "content": llm_content,
                            "duration": audio_duration
                        }
                        logger.info(f"连续三次未匹配，强制匹配动作组1: {matched_result['action_name']}")
            else:
                # 重置未匹配计数
                Audio.no_match_count = 0
            
            # 如果有匹配结果，添加时间戳并存入队列
            if matched_result:
                # 原始代码
                # import time
                # matched_result["timestamp"] = int(time.time())
                # matched_result["id"] = len(Audio.action_mapping_queue) + 1
                
                # 添加到队列中
                # Audio.action_mapping_queue.append(matched_result)
                
                # 如果队列超出最大长度，删除最早的记录
                # if len(Audio.action_mapping_queue) > Audio.action_mapping_queue_max_size:
                #     Audio.action_mapping_queue.pop(0)
                
                # 使用UnityQueueHandler添加动作映射
                from main import unity_queue_handler
                unity_queue_handler.add_action_mapping(matched_result)
                
                logger.info(f"最终动作映射结果: {matched_result}")
            else:
                logger.info("没有匹配到任何动作")
            
            return matched_result
            
        except Exception as e:
            logger.error(f"动作映射处理出错: {e}")
            logger.error(traceback.format_exc())
            return None

    # 获取动作映射队列 - 这个方法应该被删除或重定向到UnityQueueHandler
    def get_action_mapping_queue(self, limit=None):
        """
        获取动作映射结果缓存队列
        这个方法现在是重定向到全局的UnityQueueHandler
        
        Args:
            limit: 返回的记录数量限制，None表示返回全部
            
        Returns:
            dict: 包含动作映射记录的字典
        """
        try:
            from main import unity_queue_handler
            return unity_queue_handler.get_action_mapping_queue(limit)
        except Exception as e:
            logger.error(f"获取动作映射队列出错: {e}")
            return {"data": [], "count": 0}
    
    # 删除动作映射队列中的记录 - 这个方法应该被删除或重定向到UnityQueueHandler
    def delete_action_mapping(self, action_id=None, delete_all=False):
        """
        删除动作映射队列中的记录
        这个方法现在是重定向到全局的UnityQueueHandler
        
        参数:
            action_id: 要删除的动作ID，None表示不按ID删除
            delete_all: 是否删除所有记录
            
        返回:
            bool: 是否删除成功
        """
        try:
            from main import unity_queue_handler
            return unity_queue_handler.delete_action_mapping(action_id, delete_all)
        except Exception as e:
            logger.error(f"删除动作映射记录出错: {e}")
            logger.error(traceback.format_exc())
            return False

    # 将本地文件路径转换为URL
    def convert_path_to_url(self, file_path):
        """
        将本地文件路径转换为URL
        例如：E:\GitHub_pro\AI-Vtuber\out\gpt_sovits_7.wav 
        转换为 http://127.0.0.1:8081/out/gpt_sovits_7.wav
        
        参数:
            file_path: 本地文件路径
            
        返回:
            str: 转换后的URL
        """
        try:
            if not file_path:
                return ""
                
            # 获取WebUI的IP和端口
            webui_ip = self.config.get("webui", "ip")
            webui_port = self.config.get("webui", "port")
            
            # 如果IP是0.0.0.0，使用127.0.0.1替代
            if webui_ip == "0.0.0.0":
                webui_ip = "127.0.0.1"
            
            # 获取工作目录的绝对路径
            import os
            workspace_path = os.path.abspath(".")
            
            # 将文件路径转换为相对于工作目录的路径
            relative_path = os.path.relpath(file_path, workspace_path)
            # 替换反斜杠为正斜杠
            relative_path = relative_path.replace("\\", "/")
            
            # 构建URL
            url = f"http://{webui_ip}:{webui_port}/{relative_path}"
            
            logger.debug(f"转换文件路径: {file_path} -> URL: {url}")
            
            return url
        except Exception as e:
            logger.error(f"转换文件路径为URL时出错: {e}")
            logger.error(traceback.format_exc())
            return ""

