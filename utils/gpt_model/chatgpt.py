import traceback
from copy import deepcopy
import openai
from packaging import version

from utils.common import Common
from utils.my_log import logger


class Chatgpt:
    # 设置会话初始值
    # session_config = {'msg': [{"role": "system", "content": config_data['chatgpt']['preset']}]}
    session_config = {}
    sessions = {}
    current_key_index = 0
    data_openai = {}
    data_chatgpt = {}

    def __init__(self, data_openai: dict=None, data_chatgpt: dict=None):
        self.common = Common()

        import json
        # 直接写死从配置文件config.json中获取
        with open("config.json", 'r', encoding="utf-8") as f:
            self.config = json.load(f)

        self.data_chatgpt = self.config.get("chatgpt", {})
        self.data_openai = self.config.get("openai", {})

        # logger.warning(f"data_chatgpt={self.data_chatgpt}")
        # logger.warning(f"data_openai={self.data_openai}")

        self.preset = self.data_chatgpt.get("preset", "")
        logger.warning(f"preset={self.preset}")

        if data_chatgpt and data_chatgpt != {}:
            # 设置会话初始值
            self.session_config = {'msg': []}
            # self.session_config = {'msg': [{"role": "system", "content": data_chatgpt["preset"]}]}
        else:
            self.session_config = {'msg': []}


    # chatgpt相关
    def chat(self, msg, sessionid, save_history=False):
        """
        ChatGPT 对话函数
        :param msg: 用户输入的消息
        :param sessionid: 当前会话 ID
        :param save_history: 是否保存会话历史，默认为False
        :return: ChatGPT 返回的回复内容
        """
        try:
            import json
            # 直接写死从配置文件config.json中获取
            with open("config.json", 'r', encoding="utf-8") as f:
                self.config = json.load(f)
                
            # logger.warning(f"data_chatgpt={self.data_chatgpt}")
            # logger.warning(f"data_openai={self.data_openai}")
            
            # 获取当前会话
            session = self.get_chat_session(sessionid)

            # 将用户输入的消息添加到会话中
            session['msg'].append({"role": "user", "content": self.preset + "\n" + msg})

            # 添加当前时间到会话中
            # session['msg'][1] = {"role": "system", "content": "current time is:" + self.common.get_bj_time()}

            # 调用 ChatGPT 接口生成回复消息
            message = self.chat_with_gpt(session['msg'])

            if message is None:
                return None

            # 如果返回的消息包含最大上下文长度限制，则删除超长上下文并重试
            if message.__contains__("This model's maximum context length is 409"):
                del session['msg'][0:3]
                del session['msg'][len(session['msg']) - 1:len(session['msg'])]
                message = self.chat(msg, sessionid, save_history)

            # 仅当save_history为True时，才将ChatGPT返回的回复消息添加到会话中
            if save_history:
                session['msg'].append({"role": "assistant", "content": message})

            # 输出会话 ID 和 ChatGPT 返回的回复消息
            logger.info("会话ID: " + str(sessionid))
            logger.debug("ChatGPT返回内容: ")
            logger.debug(message)

            # 返回 ChatGPT 返回的回复消息
            return message

        # 捕获异常并打印堆栈跟踪信息
        except Exception as error:
            logger.error(traceback.format_exc())
            return None


    def get_chat_session(self, sessionid):
        """
        获取指定 ID 的会话，如果不存在则创建一个新的会话
        :param sessionid: 会话 ID
        :return: 指定 ID 的会话
        """
        sessionid = str(sessionid)
        if sessionid not in self.sessions:
            config = deepcopy(self.session_config)
            config['id'] = sessionid
            # config['msg'].append({"role": "system", "content": "current time is:" + self.common.get_bj_time()})
            self.sessions[sessionid] = config
        return self.sessions[sessionid]


    def chat_with_gpt(self, messages):
        """
        使用 ChatGPT 接口生成回复消息
        :param messages: 上下文消息列表
        :return: ChatGPT 返回的回复消息
        """
        max_length = len(self.data_openai['api_key']) - 1

        try:
            openai.api_base = self.data_openai['api']

            if not self.data_openai['api_key']:
                logger.error(f"请设置openai Api Key")
                return None
            else:
                # 判断是否所有 API key 均已达到速率限制
                if self.current_key_index > max_length:
                    self.current_key_index = 0
                    logger.warning(f"全部Key均已达到速率限制,请等待一分钟后再尝试")
                    return None
                openai.api_key = self.data_openai['api_key'][self.current_key_index]

            logger.debug(f"openai.__version__={openai.__version__}")

            # 判断openai库版本，1.x.x和0.x.x有破坏性更新
            if version.parse(openai.__version__) < version.parse('1.0.0'):
                # 调用 ChatGPT 接口生成回复消息
                resp = openai.ChatCompletion.create(
                    model=self.data_chatgpt['model'],
                    messages=messages,
                    timeout=30
                )

                resp = resp['choices'][0]['message']['content']
            else:
                logger.debug(f"base_url={openai.api_base}, api_key={openai.api_key}")

                client = openai.OpenAI(base_url=openai.api_base, api_key=openai.api_key)
                # 调用 ChatGPT 接口生成回复消息
                resp = client.chat.completions.create(
                    model=self.data_chatgpt['model'],
                    messages=messages,
                    timeout=30
                )

                resp = resp.choices[0].message.content
        # 处理 OpenAIError 异常
        except openai.OpenAIError as e:
            if str(e).__contains__("Rate limit reached for default-gpt-3.5-turbo") and self.current_key_index <= max_length:
                self.current_key_index = self.current_key_index + 1
                logger.warning("速率限制，尝试切换key")
                msg = self.chat_with_gpt(messages)
                return msg
            elif str(e).__contains__(
                    "Your access was terminated due to violation of our policies") and self.current_key_index <= max_length:
                logger.warning("请及时确认该Key: " + str(openai.api_key) + " 是否正常，若异常，请移除")

                # 判断是否所有 API key 均已尝试
                if self.current_key_index + 1 > max_length:
                    return str(e)
                else:
                    logger.warning("访问被阻止，尝试切换Key")
                    self.current_key_index = self.current_key_index + 1
                    msg = self.chat_with_gpt(messages)
                    return msg
            else:
                logger.error('openai 接口报错: ' + str(e))
                return None

        return resp

    def chat_stream(self, msg, sessionid):
        """
        ChatGPT 流式对话函数
        :param msg: 用户输入的消息
        :param sessionid: 当前会话 ID
        :return: resp - 响应消息
        注意: 该方法仅返回流式响应，不会将AI回复添加到会话历史中
        """
        try:
            # 获取当前会话
            session = self.get_chat_session(sessionid)

            # 将用户输入的消息添加到会话中
            session['msg'].append({"role": "user", "content": self.preset + "\n" + msg})

            # 添加当前时间到会话中
            # session['msg'][1] = {"role": "system", "content": "current time is:" + self.common.get_bj_time()}

            # logger.warning(sessionid)
            # logger.warning(session)

            messages = session['msg']

            max_length = len(self.data_openai['api_key']) - 1

            openai.api_base = self.data_openai['api']

            if not self.data_openai['api_key']:
                logger.error(f"请设置openai Api Key")
                return None
            else:
                # 判断是否所有 API key 均已达到速率限制
                if self.current_key_index > max_length:
                    self.current_key_index = 0
                    logger.warning(f"全部Key均已达到速率限制,请等待一分钟后再尝试")
                    return None
                openai.api_key = self.data_openai['api_key'][self.current_key_index]

            logger.debug(f"openai.__version__={openai.__version__}")

            # 判断openai库版本，1.x.x和0.x.x有破坏性更新
            if version.parse(openai.__version__) < version.parse('1.0.0'):
                # 调用 ChatGPT 接口生成回复消息
                resp = openai.ChatCompletion.create(
                    model=self.data_chatgpt['model'],
                    messages=messages,
                    timeout=30,
                    stream=True,
                )

            else:
                logger.debug(f"base_url={openai.api_base}, api_key={openai.api_key}")

                client = openai.OpenAI(base_url=openai.api_base, api_key=openai.api_key)
                # 调用 ChatGPT 接口生成回复消息
                resp = client.chat.completions.create(
                    model=self.data_chatgpt['model'],
                    messages=messages,
                    timeout=30,
                    stream=True,
                )

            # 注意：这里不会将流式响应添加到会话历史中
            return resp

        except Exception as e:
            logger.error(traceback.format_exc())
            return None


    # 调用gpt接口，获取返回内容
    def get_gpt_resp(self, username, prompt, stream=False, save_history=False):
        """
        调用GPT接口获取回复内容
        :param username: 用户名/会话ID
        :param prompt: 提示词
        :param stream: 是否使用流式返回
        :param save_history: 是否保存会话历史，默认为False
        :return: ChatGPT返回的内容
        """
        try:
            self.data_chatgpt = self.config.get("chatgpt", {})
            self.data_openai = self.config.get("openai", {})

            # logger.warning(f"data_chatgpt={self.data_chatgpt}")
            # logger.warning(f"data_openai={self.data_openai}")
            
            if not stream:
                # 调用 ChatGPT 接口生成回复消息
                resp_content = self.chat(prompt, username, save_history)
            else:
                resp_content = self.chat_stream(prompt, username)

            return resp_content
        except Exception as e:
            logger.error(traceback.format_exc())
            return None
    
    # 处理带图像的请求
    def get_resp_with_img(self, prompt, img_data):
        """
        使用OpenAI标准接口处理带图像的请求
        
        Args:
            prompt: 文本内容
            img_data: 图片数据，可以是图片路径字符串或已编码的图片数据
            
        Returns:
            OpenAI接口的响应内容
        """
        try:
            import json
            # 直接写死从配置文件config.json中获取
            with open("config.json", 'r', encoding="utf-8") as f:
                self.config = json.load(f)

            self.data_chatgpt = self.config.get("image_recognition", {})
            self.data_chatgpt = self.data_chatgpt.get("openai", {})
            self.data_openai = self.data_chatgpt

            new_prompt = self.data_chatgpt.get("preset", "")
            if new_prompt != "":
                prompt = new_prompt

            logger.warning(f"data_chatgpt={self.data_chatgpt}")
            # logger.warning(f"data_openai={self.data_openai}")
            
            # 检查 img_data 的类型
            if isinstance(img_data, str):  # 如果是字符串，假定为文件路径
                import base64

                # logger.warning(f"img_data is a string: {img_data}")

                # 读取本地图片文件
                with open(img_data, "rb") as image_file:
                    # 将图片内容转换为base64编码
                    img = base64.b64encode(image_file.read()).decode("utf-8")
            else:
                img = img_data

            # 检查OpenAI API密钥
            max_length = len(self.data_openai['api_key']) - 1

            if not self.data_openai['api_key']:
                logger.error("请设置openai Api Key")
                return None
            else:
                # 判断是否所有 API key 均已达到速率限制
                if self.current_key_index > max_length:
                    self.current_key_index = 0
                    logger.warning("全部Key均已达到速率限制,请等待一分钟后再尝试")
                    return None
                
            # 设置API基础URL和密钥
            openai.api_base = self.data_openai['api']
            openai.api_key = self.data_openai['api_key'][self.current_key_index]
            
            logger.debug(f"openai.__version__={openai.__version__}")

            logger.warning(f"VL调用的提示词为：{prompt}")
            
            # 准备消息
            messages = [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}
                    ]
                }
            ]
            
            # 判断openai库版本，1.x.x和0.x.x有破坏性更新
            if version.parse(openai.__version__) >= version.parse('1.0.0'):
                logger.info(f"base_url={openai.api_base}, api_key={openai.api_key}")
                
                client = openai.OpenAI(base_url=openai.api_base, api_key=openai.api_key)
                
                # 调用OpenAI接口
                response = client.chat.completions.create(
                    model=self.data_chatgpt.get("model", "gpt-4-vision-preview"),
                    messages=messages,
                    max_tokens=self.data_chatgpt.get("max_tokens", 500),
                    timeout=60,
                    # stream=True
                )
                
                resp_content = response.choices[0].message.content
            else:
                # 旧版OpenAI库不支持vision API，返回错误
                logger.error("OpenAI库版本过低，不支持图像处理功能，请升级到1.0.0以上版本")
                return "OpenAI库版本过低，不支持图像处理功能，请升级到1.0.0以上版本"
            
            logger.debug(f"resp_content={resp_content}")
            
            return resp_content
            
        except openai.OpenAIError as e:
            if str(e).__contains__("Rate limit reached") and self.current_key_index <= max_length:
                self.current_key_index = self.current_key_index + 1
                logger.warning("速率限制，尝试切换key")
                msg = self.get_resp_with_img(prompt, img_data)
                return msg
            elif str(e).__contains__("Your access was terminated") and self.current_key_index <= max_length:
                logger.warning("请及时确认该Key: " + str(openai.api_key) + " 是否正常，若异常，请移除")
                
                # 判断是否所有 API key 均已尝试
                if self.current_key_index + 1 > max_length:
                    return str(e)
                else:
                    logger.warning("访问被阻止，尝试切换Key")
                    self.current_key_index = self.current_key_index + 1
                    msg = self.get_resp_with_img(prompt, img_data)
                    return msg
            else:
                logger.error('openai 接口报错: ' + str(e))
                return None
                
        except Exception as e:
            logger.error(traceback.format_exc())
            return None
        
    # 添加AI返回消息到会话，用于提供上下文记忆
    def add_assistant_msg_to_session(self, username, message):
        try:
            return {"ret": True}
            # 获取当前用户的会话
            session = self.get_chat_session(str(username))
            # 将 ChatGPT 返回的回复消息添加到会话中
            session['msg'].append({"role": "assistant", "content": message})

            # logger.warning(str(username))
            # logger.warning(session)

            return {"ret": True}
        except Exception as e:
            logger.error(traceback.format_exc())
            return {"ret": False}

