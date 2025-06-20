import os
import threading
import schedule
import random
import asyncio, aiohttp
import traceback
import copy
import json, re

from functools import partial

from typing import *

# 按键监听语音聊天板块
import keyboard
import pyaudio
import wave
import numpy as np
import speech_recognition as sr
from aip import AipSpeech
import signal
import time

import http.server
import socketserver

from utils.my_log import logger
from utils.common import Common
from utils.config import Config
from utils.my_handle import My_handle
import utils.my_global as my_global

"""
	___ _                       
	|_ _| | ____ _ _ __ ___  ___ 
	 | || |/ / _` | '__/ _ \/ __|
	 | ||   < (_| | | | (_) \__ \
	|___|_|\_\__,_|_|  \___/|___/

"""

config = None
common = None
my_handle = None


# 配置文件路径
config_path = "config.json"




"""
                       _oo0oo_
                      o8888888o
                      88" . "88
                      (| -_- |)
                      0\  =  /0
                    ___/`---'\___
                  .' \\|     |// '.
                 / \\|||  :  |||// \
                / _||||| -:- |||||- \
               |   | \\\  - /// |   |
               | \_|  ''\---/''  |_/ |
               \  .-\__  '-'  ___/-. /
             ___'. .'  /--.--\  `. .'___
          ."" '<  `.___\_<|>_/___.' >' "".
         | | :  `- \`.;`\ _ /`;.`/ - ` : | |
         \  \ `_.   \_ __\ /__ _/   .-` /  /
     =====`-.____`.___ \_____/___.-`___.-'=====
                       `=---='


     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

         佛祖保佑       永不宕机     永无BUG
"""


# 点火起飞
def start_server():
    global \
        config, \
        common, \
        my_handle, \
        config_path
    global do_listen_and_comment_thread, stop_do_listen_and_comment_thread_event
    global faster_whisper_model, sense_voice_model, is_recording, is_talk_awake

    # 按键监听相关
    do_listen_and_comment_thread = None
    stop_do_listen_and_comment_thread_event = threading.Event()
    # 冷却时间 0.5 秒
    cooldown = 0.5
    last_pressed = 0
    # 正在录音中 标志位
    is_recording = False
    # 聊天是否唤醒
    is_talk_awake = False

    # 待播放音频数量（在使用 音频播放器 或者 metahuman-stream等不通过AI Vtuber播放音频的对接项目时，使用此变量记录是是否还有音频没有播放完）
    my_global.wait_play_audio_num = 0
    my_global.wait_synthesis_msg_num = 0

    # 获取 httpx 库的日志记录器
    # httpx_logger = logging.getLogger("httpx")
    # 设置 httpx 日志记录器的级别为 WARNING
    # httpx_logger.setLevel(logging.WARNING)

    # 最新的直播间数据
    my_global.last_liveroom_data = {
        "OnlineUserCount": 0,
        "TotalUserCount": 0,
        "TotalUserCountStr": "0",
        "OnlineUserCountStr": "0",
        "MsgId": 0,
        "User": None,
        "Content": "当前直播间人数 0，累计直播间人数 0",
        "RoomId": 0,
    }
    # 最新入场的用户名列表
    my_global.last_username_list = [""]

    my_handle = My_handle(config_path)
    if my_handle is None:
        logger.error("程序初始化失败！")
        os._exit(0)

    # Live2D线程

    if platform != "wxlive":
        """

                  /@@@@@@@@          @@@@@@@@@@@@@@@].      =@@@@@@@       
                 =@@@@@@@@@^         @@@@@@@@@@@@@@@@@@`    =@@@@@@@       
                ,@@@@@@@@@@@`        @@@@@@@@@@@@@@@@@@@^   =@@@@@@@       
               .@@@@@@\@@@@@@.       @@@@@@@^   .\@@@@@@\   =@@@@@@@       
               /@@@@@/ \@@@@@\       @@@@@@@^    =@@@@@@@   =@@@@@@@       
              =@@@@@@. .@@@@@@^      @@@@@@@\]]]@@@@@@@@^   =@@@@@@@       
             ,@@@@@@^   =@@@@@@`     @@@@@@@@@@@@@@@@@@/    =@@@@@@@       
            .@@@@@@@@@@@@@@@@@@@.    @@@@@@@@@@@@@@@@/`     =@@@@@@@       
            /@@@@@@@@@@@@@@@@@@@\    @@@@@@@^               =@@@@@@@       
           =@@@@@@@@@@@@@@@@@@@@@^   @@@@@@@^               =@@@@@@@       
          ,@@@@@@@.       ,@@@@@@@`  @@@@@@@^               =@@@@@@@       
          @@@@@@@^         =@@@@@@@. @@@@@@@^               =@@@@@@@   

        """
        
        # HTTP API线程
        def http_api_thread():
            import uvicorn
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            from utils.models import (
                SendMessage,
                LLMMessage,
                CallbackMessage,
                CommonResult,
            )

            # 定义FastAPI应用
            app = FastAPI()

            # 允许跨域
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

            # 定义POST请求路径和处理函数
            @app.post("/send")
            async def send(msg: SendMessage):
                global my_handle, config

                try:
                    tmp_json = msg.dict()
                    logger.info(f"内部HTTP API send接口收到数据：{tmp_json}")
                    data_json = tmp_json["data"]
                    if "type" not in data_json:
                        data_json["type"] = tmp_json["type"]

                    if data_json["type"] in ["reread", "reread_top_priority"]:
                        my_handle.reread_handle(data_json, type=data_json["type"])
                    elif data_json["type"] == "comment":
                        my_handle.process_data(data_json, "comment")
                    elif data_json["type"] == "tuning":
                        my_handle.tuning_handle(data_json)
                    elif data_json["type"] == "gift":
                        my_handle.gift_handle(data_json)
                    elif data_json["type"] == "entrance":
                        my_handle.entrance_handle(data_json)

                    return CommonResult(code=200, message="成功")
                except Exception as e:
                    logger.error(f"发送数据失败！{e}")
                    return CommonResult(code=-1, message=f"发送数据失败！{e}")

            @app.post("/llm")
            async def llm(msg: LLMMessage):
                global my_handle, config

                try:
                    data_json = msg.dict()
                    logger.info(f"API收到数据：{data_json}")

                    resp_content = my_handle.llm_handle(
                        data_json["type"], data_json, webui_show=False
                    )

                    return CommonResult(
                        code=200, message="成功", data={"content": resp_content}
                    )
                except Exception as e:
                    logger.error(f"调用LLM失败！{e}")
                    return CommonResult(code=-1, message=f"调用LLM失败！{e}")

            from starlette.requests import Request

            @app.post('/tts')
            async def tts(request: Request):
                try:
                    data_json = await request.json()
                    logger.info(f"API收到数据：{data_json}")

                    resp_json = await My_handle.audio.tts_handle(data_json)

                    return {"code": 200, "message": "成功", "data": resp_json}
                except Exception as e:
                    logger.error(traceback.format_exc())
                    return CommonResult(code=-1, message=f"失败！{e}")
                
            @app.post("/callback")
            async def callback(msg: CallbackMessage):
                global my_handle, config

                try:
                    data_json = msg.dict()

                    # 特殊回调特殊处理
                    if data_json["type"] == "audio_playback_completed":
                        my_global.wait_play_audio_num = int(data_json["data"]["wait_play_audio_num"])
                        my_global.wait_synthesis_msg_num = int(data_json["data"]["wait_synthesis_msg_num"])
                        logger.info(f"内部HTTP API callback接口 音频播放完成回调，待播放音频数量：{my_global.wait_play_audio_num}，待合成消息数量：{my_global.wait_synthesis_msg_num}")
                    else:
                        logger.info(f"内部HTTP API callback接口收到数据：{data_json}")

                    # 音频播放完成
                    if data_json["type"] in ["audio_playback_completed"]:
                        my_global.wait_play_audio_num = int(data_json["data"]["wait_play_audio_num"])

                        # 如果等待播放的音频数量大于10
                        if data_json["data"]["wait_play_audio_num"] > int(
                            config.get(
                                "idle_time_task", "wait_play_audio_num_threshold"
                            )
                        ):
                            logger.info(
                                f'等待播放的音频数量大于限定值，闲时任务的闲时计时由 {my_global.global_idle_time} -> {int(config.get("idle_time_task", "idle_time_reduce_to"))}秒'
                            )
                            # 闲时任务的闲时计时 清零
                            my_global.global_idle_time = int(
                                config.get("idle_time_task", "idle_time_reduce_to")
                            )

                    return CommonResult(code=200, message="callback处理成功！")
                except Exception as e:
                    logger.error(f"callback处理失败！{e}")
                    return CommonResult(code=-1, message=f"callback处理失败！{e}")

            # 获取系统信息接口
            @app.get("/get_sys_info")
            async def get_sys_info():
                global my_handle, config

                try:
                    data = {
                        "audio": my_handle.get_audio_info(),
                        "metahuman-stream": {
                            "wait_play_audio_num": my_global.wait_play_audio_num,
                            "wait_synthesis_msg_num": my_global.wait_synthesis_msg_num,
                        }
                    }

                    return CommonResult(code=200, data=data, message="get_sys_info处理成功！")
                except Exception as e:
                    logger.error(f"get_sys_info处理失败！{e}")
                    return CommonResult(code=-1, message=f"get_sys_info处理失败！{e}")

            

            logger.info("HTTP API线程已启动！")

            # 将本地目录中的静态文件（如 CSS、JavaScript、图片等）暴露给 web 服务器，以便用户可以通过特定的 URL 访问这些文件。
            if config.get("webui", "local_dir_to_endpoint", "enable"):
                for tmp in config.get("webui", "local_dir_to_endpoint", "config"):
                    from fastapi.staticfiles import StaticFiles
                    app.mount(tmp['url_path'], StaticFiles(directory=tmp['local_dir']), name=tmp['local_dir'])
                    
            uvicorn.run(app, host="0.0.0.0", port=config.get("api_port"))
            #uvicorn.run(app, host="0.0.0.0", port=config.get("api_port"), ssl_certfile="F:\\FunASR_WS\\cert.pem", ssl_keyfile="F:\\FunASR_WS\\key.pem")

        # HTTP API线程并启动
        inside_http_api_thread = threading.Thread(target=http_api_thread)
        inside_http_api_thread.start()

    

    
    
    logger.info(f"当前平台：{platform}")


    if platform == "bilibili2":
        from utils.platforms.bilibili2 import start_listen



# 退出程序
def exit_handler(signum, frame):
    logger.info("收到信号:", signum)


if __name__ == "__main__":
    common = Common()
    config = Config(config_path)
    # 日志文件路径
    log_path = "./log/log-" + common.get_bj_time(1) + ".txt"
    # Configure_logger(log_path)

    platform = config.get("platform")




    # 信号特殊处理
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    start_server()
