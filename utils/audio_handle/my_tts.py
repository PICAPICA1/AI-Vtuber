import json, os
import aiohttp, requests, ssl, asyncio
from urllib.parse import urlencode
from gradio_client import Client
import traceback
import edge_tts
from urllib.parse import urljoin
import random, copy

from utils.common import Common
from utils.my_log import logger
from utils.config import Config

class MY_TTS:
    def __init__(self, config_path):
        self.common = Common()
        self.config = Config(config_path)

        # 创建一个不执行证书验证的 SSLContext 对象
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

        # 获取 werkzeug 库的日志记录器
        # werkzeug_logger = logger.getLogger("werkzeug")
        # # 设置 httpx 日志记录器的级别为 WARNING
        # werkzeug_logger.setLevel(logger.WARNING)

        # 请求超时
        self.timeout = 60

        # 使用内部成员做配置
        self.use_class_config = False
        # 备份一下配置
        self.class_config = copy.copy(self.config)

        try:
            self.audio_out_path = self.config.get("play_audio", "out_path")

            if not os.path.isabs(self.audio_out_path):
                if not self.audio_out_path.startswith('./'):
                    self.audio_out_path = './' + self.audio_out_path
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("请检查播放音频的音频输出路径配置！！！这将影响程序使用！")


    # 获取随机数，单数据就是原数值，有-则判断为范围性数据，随机一个数值，返回float数据
    def get_random_float(self, data):
        # 将非字符串的情况统一处理为长度相同的最小值和最大值
        if isinstance(data, str) and "-" in data:
            min, max = map(float, data.split("-"))
        else:
            min = max = float(data)
        
        # 返回指定范围内的随机浮点数
        return random.uniform(min, max)

    # 音频文件base64编码 传入文件路径
    def encode_audio_to_base64(self, file_path):
        import base64

        if file_path == "" or file_path is None:
            return None

        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()
            encoded_audio = base64.b64encode(audio_data).decode('utf-8')
        return encoded_audio

    async def download_audio(self, type: str, file_url: str, timeout: int=30, request_type: str="get", data=None, json_data=None, audio_suffix: str="wav"):
        async with aiohttp.ClientSession() as session:
            try:
                if request_type == "get":
                    async with session.get(file_url, params=data, timeout=timeout) as response:
                        if response.status == 200:
                            content = await response.read()
                            file_name = type + '_' + self.common.get_bj_time(4) + '.' + audio_suffix
                            voice_tmp_path = self.common.get_new_audio_path(self.audio_out_path, file_name)
                            with open(voice_tmp_path, 'wb') as file:
                                file.write(content)
                            return voice_tmp_path
                        else:
                            logger.error(f'{type} 下载音频失败: {response.status}')
                            return None
                else:
                    async with session.post(file_url, data=data, json=json_data, timeout=timeout) as response:
                        if response.status == 200:
                            content = await response.read()
                            file_name = type + '_' + self.common.get_bj_time(4) + '.' + audio_suffix
                            voice_tmp_path = self.common.get_new_audio_path(self.audio_out_path, file_name)
                            with open(voice_tmp_path, 'wb') as file:
                                file.write(content)
                            return voice_tmp_path
                        else:
                            logger.error(f'{type} 下载音频失败: {response.status}')
                            return None
            except asyncio.TimeoutError:
                logger.error("{type} 下载音频超时")
                return None
    async def gsvi_voice_path(self, file_url, json_data):
            try:
                resp_json = await Common.send_async_request(self,file_url,"POST", json_data , resp_data_type="json")
                if resp_json is None:
                    logger.error(f'{type} 获取音频失败: {resp_json}')
                    return None
                else:
                    logger.success(resp_json["msg"])
                    return resp_json["audio_url"]
            except asyncio.TimeoutError:
                logger.error("获取音频超时")
                return None


    # 请求Edge-TTS接口获取合成后的音频路径
    async def edge_tts_api(self, data):
        try:
            file_name = 'edge_tts_' + self.common.get_bj_time(4) + '.mp3'
            voice_tmp_path = self.common.get_new_audio_path(self.audio_out_path, file_name)
            # voice_tmp_path = './out/' + self.common.get_bj_time(4) + '.mp3'
            # 过滤" '字符
            data["content"] = data["content"].replace('"', '').replace("'", '')

            proxy = data["edge-tts"]["proxy"] if data["edge-tts"]["proxy"] != "" else None

            # 使用 Edge TTS 生成回复消息的语音文件
            communicate = edge_tts.Communicate(
                text=data["content"], 
                voice=data["edge-tts"]["voice"], 
                rate=data["edge-tts"]["rate"], 
                volume=data["edge-tts"]["volume"], 
                proxy=proxy
            )
            await communicate.save(voice_tmp_path)

            return voice_tmp_path
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(e)
            return None
        
    # 请求GSVI接口获取合成后的音频路径
    async def gsvi_api(self, data):
        try:

                # dl_url: str = ""
                # version: str = "v4"
                # model_name: str = ""
                # prompt_text_lang: str = ""
                # emotion: str = ""
                # text: str = ""
                # text_lang: str = ""
            data_json = {

                "model_name": data["model_name"],
                "prompt_text_lang": data["prompt_text_lang"],
                "emotion": data["emotion"],
                "text": data["content"],
                "text_lang": data["text_lang"],
                
            }
            API_URL = urljoin(data["api_ip_port"], '/v1/audio/speech')

            return await self.gsvi_voice_path(API_URL, data_json)

        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(e)
            return None
        


    async def gpt_sovits_api(self, data):
        import base64
        import mimetypes
        import websockets
        import asyncio

        def file_to_data_url(file_path):
            # 根据文件扩展名确定 MIME 类型
            mime_type, _ = mimetypes.guess_type(file_path)

            # 读取文件内容
            with open(file_path, "rb") as file:
                file_content = file.read()

            # 转换为 Base64 编码
            base64_encoded_data = base64.b64encode(file_content).decode('utf-8')

            # 构造完整的 Data URL
            return f"data:{mime_type};base64,{base64_encoded_data}"

               
        try:
            logger.debug(f"data={data}")
            
            if data["type"] == "v2_api_0821":
                try:
                    data_json = {
                        "text": data["content"],
                        "text_lang": data[data["type"]]["text_lang"],
                        "ref_audio_path": data[data["type"]]["ref_audio_path"],
                        "aux_ref_audio_paths": data[data["type"]]["aux_ref_audio_paths"],
                        "prompt_text": data[data["type"]]["prompt_text"],
                        "prompt_lang": data[data["type"]]["prompt_lang"],
                        "top_k": int(data[data["type"]]["top_k"]),
                        "top_p": float(data[data["type"]]["top_p"]),
                        "temperature": float(data[data["type"]]["temperature"]),
                        "text_split_method": data[data["type"]]["text_split_method"],
                        "batch_size": int(data[data["type"]]["batch_size"]),
                        "split_bucket": data[data["type"]]["split_bucket"],
                        "speed_factor": float(data[data["type"]]["speed_factor"]),
                        "fragment_interval": float(data[data["type"]]["fragment_interval"]),
                        "seed": int(data[data["type"]]["seed"]),
                        "media_type": data[data["type"]]["media_type"],
                        "streaming_mode": data[data["type"]]["streaming_mode"],
                        "parallel_infer": data[data["type"]]["parallel_infer"],
                        "repetition_penalty": float(data[data["type"]]["repetition_penalty"]),
                    }

                    API_URL = urljoin(data["api_ip_port"], '/tts')

                    return await self.download_audio("gpt_sovits", API_URL, self.timeout, "post", None, data_json)
                except aiohttp.ClientError as e:
                    logger.error(traceback.format_exc())
                    logger.error(f'gpt_sovits请求失败: {e}')
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f'gpt_sovits未知错误: {e}')
            
            
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'gpt_sovits未知错误，请检查您的gpt_sovits推理是否启动/配置是否正确，报错内容: {e}')
        
        return None


