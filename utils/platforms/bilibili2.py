import blivedm
import blivedm.models.web as web_models
import blivedm.models.open_live as open_models

import http.cookies
import json
import aiohttp
import asyncio
import traceback
from typing import Optional
import random

from utils.my_log import logger
import utils.my_global as my_global



session: Optional[aiohttp.ClientSession] = None

def start_listen(config, common, my_handle, platform: str):
    # 直播间ID的取值看直播间URL
    TEST_ROOM_IDS = [my_handle.get_room_id()]
    # 这里填一个已登录账号的cookie。不填cookie也可以连接，但是收到弹幕的用户名会打码，UID会变成0
    SESSDATA = ""

    try:
        if config.get("bilibili", "login_type") == "cookie":
            bilibili_cookie = config.get("bilibili", "cookie")
            SESSDATA = common.parse_cookie_data(bilibili_cookie, "SESSDATA")
            # logger.info(f"SESSDATA={SESSDATA}")

    except Exception as e:
        logger.error(traceback.format_exc())
        my_handle.abnormal_alarm_handle("platform")

    async def main_func():
        global session
        
        try:
            init_session()

            await run_single_client()
        finally:
            await session.close()

    def init_session():
        global session

        cookies = http.cookies.SimpleCookie()
        cookies["SESSDATA"] = SESSDATA
        cookies["SESSDATA"]["domain"] = "bilibili.com"

        # logger.info(f"SESSDATA={SESSDATA}")

        # logger.warning(f"sessdata={SESSDATA}")
        # logger.warning(f"cookies={cookies}")

        session = aiohttp.ClientSession()
        session.cookie_jar.update_cookies(cookies)

    async def run_single_client():
        """
        演示监听一个直播间
        """
        global session
        
        room_id = random.choice(TEST_ROOM_IDS)
        client = blivedm.BLiveClient(room_id, session=session)
        handler = MyHandler()
        client.set_handler(handler)

        client.start()
        try:
            # 演示5秒后停止
            await asyncio.sleep(5)
            client.stop()

            await client.join()
        finally:
            await client.stop_and_close()


    class MyHandler(blivedm.BaseHandler):
        # 演示如何添加自定义回调
        _CMD_CALLBACK_DICT = blivedm.BaseHandler._CMD_CALLBACK_DICT.copy()

        # 入场消息回调
        def __interact_word_callback(
            self, client: blivedm.BLiveClient, command: dict
        ):
            # logger.info(f"[{client.room_id}] INTERACT_WORD: self_type={type(self).__name__}, room_id={client.room_id},"
            #     f" uname={command['data']['uname']}")


            my_global.idle_time_auto_clear(config, "entrance")

            username = command["data"]["uname"]

            logger.info(f"用户：{username} 进入直播间")

            # 添加用户名到最新的用户名列表
            my_global.add_username_to_last_username_list(username)

            data = {
                "platform": platform,
                "username": username,
                "content": "进入直播间",
            }

            my_handle.process_data(data, "entrance")

        _CMD_CALLBACK_DICT["INTERACT_WORD"] = __interact_word_callback  # noqa

        def _on_heartbeat(
            self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage
        ):
            logger.debug(f"[{client.room_id}] 心跳")

        def _on_danmaku(
            self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage
        ):
            # 闲时计数清零
            my_global.idle_time_auto_clear(config, "comment")

            # logger.info(f'[{client.room_id}] {message.uname}：{message.msg}')
            content = message.msg  # 获取弹幕内容
            username = message.uname  # 获取发送弹幕的用户昵称
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None

            logger.info(f"[{username}]: {content}")

            data = {
                "platform": platform,
                "username": username,
                "user_face": user_face,
                "content": content,
            }

            my_handle.process_data(data, "comment")

        def _on_gift(
            self, client: blivedm.BLiveClient, message: web_models.GiftMessage
        ):
            # logger.info(f'[{client.room_id}] {message.uname} 赠送{message.gift_name}x{message.num}'
            #     f' （{message.coin_type}瓜子x{message.total_coin}）')
            my_global.idle_time_auto_clear(config, "gift")

            gift_name = message.gift_name
            username = message.uname
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None

            # 礼物数量
            combo_num = message.num
            # 总金额
            combo_total_coin = message.total_coin

            logger.info(
                f"用户：{username} 赠送 {combo_num} 个 {gift_name}，总计 {combo_total_coin}电池"
            )

            data = {
                "platform": platform,
                "gift_name": gift_name,
                "username": username,
                "user_face": user_face,
                "num": combo_num,
                "unit_price": combo_total_coin / combo_num / 1000,
                "total_price": combo_total_coin / 1000,
            }

            my_handle.process_data(data, "gift")

        def _on_buy_guard(
            self, client: blivedm.BLiveClient, message: web_models.GuardBuyMessage
        ):
            logger.info(
                f"[{client.room_id}] {message.username} 购买{message.gift_name}"
            )

        def _on_super_chat(
            self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage
        ):
            # logger.info(f'[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}：{message.message}')
            my_global.idle_time_auto_clear(config, "gift")

            message = message.message
            uname = message.uname
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None
            price = message.price

            logger.info(f"用户：{uname} 发送 {price}元 SC：{message}")

            data = {
                "platform": platform,
                "gift_name": "SC",
                "username": uname,
                "user_face": user_face,
                "num": 1,
                "unit_price": price,
                "total_price": price,
                "content": message,
            }

            my_handle.process_data(data, "gift")

            my_handle.process_data(data, "comment")

    class MyHandler2(blivedm.BaseHandler):
        def _on_heartbeat(
            self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage
        ):
            logger.debug(f"[{client.room_id}] 心跳")

        def _on_open_live_danmaku(
            self,
            client: blivedm.OpenLiveClient,
            message: open_models.DanmakuMessage,
        ):
            # 闲时计数清零
            my_global.idle_time_auto_clear(config, "comment")

            # logger.info(f'[{client.room_id}] {message.uname}：{message.msg}')
            content = message.msg  # 获取弹幕内容
            username = message.uname  # 获取发送弹幕的用户昵称
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None

            logger.debug(f"用户：{username} 头像：{user_face}")

            logger.info(f"[{username}]: {content}")

            data = {
                "platform": platform,
                "username": username,
                "user_face": user_face,
                "content": content,
            }

            my_handle.process_data(data, "comment")

        def _on_open_live_gift(
            self, client: blivedm.OpenLiveClient, message: open_models.GiftMessage
        ):
            my_global.idle_time_auto_clear(config, "gift")

            gift_name = message.gift_name
            username = message.uname
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None
            # 礼物数量
            combo_num = message.gift_num
            # 总金额
            combo_total_coin = message.price * message.gift_num

            logger.info(
                f"用户：{username} 赠送 {combo_num} 个 {gift_name}，总计 {combo_total_coin}电池"
            )

            data = {
                "platform": platform,
                "gift_name": gift_name,
                "username": username,
                "user_face": user_face,
                "num": combo_num,
                "unit_price": combo_total_coin / combo_num / 1000,
                "total_price": combo_total_coin / 1000,
            }

            my_handle.process_data(data, "gift")

        def _on_open_live_buy_guard(
            self,
            client: blivedm.OpenLiveClient,
            message: open_models.GuardBuyMessage,
        ):
            logger.info(
                f"[{client.room_id}] {message.user_info.uname} 购买 大航海等级={message.guard_level}"
            )

        def _on_open_live_super_chat(
            self,
            message: open_models.SuperChatMessage,
        ):
            my_global.idle_time_auto_clear(config, "gift")

            logger.info(
                f"[{message.room_id}] 醒目留言 ¥{message.rmb} {message.uname}：{message.message}"
            )

            message = message.message
            uname = message.uname
            # 检查是否存在 face 属性
            user_face = message.face if hasattr(message, "face") else None
            price = message.rmb

            logger.info(f"用户：{uname} 发送 {price}元 SC：{message}")

            data = {
                "platform": platform,
                "gift_name": "SC",
                "username": uname,
                "user_face": user_face,
                "num": 1,
                "unit_price": price,
                "total_price": price,
                "content": message,
            }

            my_handle.process_data(data, "gift")

            my_handle.process_data(data, "comment")

        def _on_open_live_super_chat_delete(
            self,
            message: open_models.SuperChatDeleteMessage,
        ):
            logger.info(
                f"[直播间 {message.room_id}] 删除醒目留言 message_ids={message.message_ids}"
            )

        def _on_open_live_like(
            self, client: blivedm.OpenLiveClient, message: open_models.LikeMessage
        ):
            logger.info(f"用户：{message.uname} 点了个赞")

    asyncio.run(main_func())
