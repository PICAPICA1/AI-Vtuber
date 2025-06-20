from nicegui import ui, app
import sys, os, json, subprocess, importlib, re, threading, signal
import traceback
import time
import asyncio
from urllib.parse import urljoin
from pathlib import Path

# from functools import partial

from utils.my_log import logger
from utils.config import Config 
from utils.common import Common
from utils.audio import Audio

"""

@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@.:;;;++;;;;:,@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@:;+++++;;++++;;;.@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@:++++;;;;;;;;;;+++;,@@@@@@@@@@@@@@@@@
@@@@@@@@@@@.;+++;;;;;;;;;;;;;;++;:@@@@@@@@@@@@@@@@
@@@@@@@@@@;+++;;;;;;;;;;;;;;;;;;++;:@@@@@@@@@@@@@@
@@@@@@@@@:+++;;;;;;;;;;;;;;;;;;;;++;.@@@@@@@@@@@@@
@@@@@@@@;;+;;;;;;;;;;;;;;;;;;;;;;;++:@@@@@@@@@@@@@
@@@@@@@@;+;;;;:::;;;;;;;;;;;;;;;;:;+;,@@@@@@@@@@@@
@@@@@@@:+;;:;;:::;:;;:;;;;::;;:;:::;+;.@@@@@@@@@@@
@@@@@@.;+;::;:,:;:;;+:++:;:::+;:::::++:+@@@@@@@@@@
@@@@@@:+;;:;;:::;;;+%;*?;;:,:;*;;;;:;+;:@@@@@@@@@@
@@@@@@;;;+;;+;:;;;+??;*?++;,:;+++;;;:++:@@@@@@@@@@
@@@@@.++*+;;+;;;;+?;?**??+;:;;+.:+;;;;+;;@@@@@@@@@
@@@@@,+;;;;*++*;+?+;**;:?*;;;;*:,+;;;;+;,@@@@@@@@@
@@@@@,:,+;+?+?++?+;,?#%*??+;;;*;;:+;;;;+:@@@@@@@@@
@@@@@@@:+;*?+?#%;;,,?###@#+;;;*;;,+;;;;+:@@@@@@@@@
@@@@@@@;+;??+%#%;,,,;SSS#S*+++*;..:+;?;+;@@@@@@@@@
@@@@@@@:+**?*?SS,,,,,S#S#+***?*;..;?;**+;@@@@@@@@@
@@@@@@@:+*??*??S,,,,,*%SS+???%++;***;+;;;.@@@@@@@@
@@@@@@@:*?*;*+;%:,,,,;?S?+%%S?%+,:?;+:,,,@@@@@@@@
@@@@@@@,*?,;+;+S:,,,,%?+;S%S%++:+??+:,,,:@@@@@@@@
@@@@@@@,:,@;::;+,,,,,+?%*+S%#?*???*;,,,,,.@@@@@@@@
@@@@@@@@:;,::;;:,,,,,,,,,?SS#??*?+,.,,,:,@@@@@@@@@
@@@@@@;;+;;+:,:%?%*;,,,,SS#%*??%,.,,,,,:@@@@@@@@@
@@@@@.+++,++:;???%S?%;.+#####??;.,,,,,,:@@@@@@@@@
@@@@@:++::??+S#??%#??S%?#@#S*+?*,,,,,,:,@@@@@@@@@@
@@@@@:;;:*?;+%#%?S#??%SS%+#%..;+:,,,,,,@@@@@@@@@@@
@@@@@@,,*S*;?SS?%##%?S#?,.:#+,,+:,,,,,,@@@@@@@@@@@
@@@@@@@;%?%#%?*S##??##?,..*#,,+:,,;*;.@@@@@@@@@@@
@@@@@@.*%??#S*?S#@###%;:*,.:#:,+;:;*+:@@@@@@@@@@@@
@@@@@@,%S??SS%##@@#%S+..;;.,#*;???*?+++:@@@@@@@@@@
@@@@@@:S%??%####@@S,,*,.;*;+#*;+?%??#S%+.@@@@@@@@@
@@@@@@:%???%@###@@?,,:**S##S*;.,%S?;+*?+.,..@@@@@@
@@@@@@;%??%#@###@@#:.;@@#@%%,.,%S*;++*++++;.@@@@@
@@@@@@,%S?S@@###@@@%+#@@#@?;,.:?;??++?%?***+.@@@@@
@@@@@@.*S?S####@@####@@##@?..:*,+:??**%+;;;;..@@@@
@@@@@@:+%?%####@@####@@#@%;:.;;:,+;?**;++;,:;:,@@@
@@@@@@;;*%?%@##@@@###@#S#*:;*+,;.+***?******+:.@@@
@@@@@@:;:??%@###%##@#%++;+*:+;,:;+%?*;+++++;:.@@@@
@@@@@@.+;:?%@@#%;+S*;;,:::**+,;:%??*+.@....@@@@@@@
@@@@@@@;*::?#S#S+;,..,:,;:?+?++*%?+::@@@@@@@@@@@@@
@@@@@@@.+*+++?%S++...,;:***??+;++:.@@@@@@@@@@@@@@@
@@@@@@@@:::..,;+*+;;+*?**+;;;+;:.@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@,+*++;;:,..@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@::,.@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

"""


"""
全局变量
"""

# 创建一个全局变量，用于表示程序是否正在运行
running_flag = False

# 定义一个标志变量，用来追踪定时器的运行状态
loop_screenshot_timer_running = False
loop_screenshot_timer = None

common = None
config = None
audio = None
my_handle = None
config_path = None

# 存储运行的子进程
my_subprocesses = {}



# 聊天记录计数
scroll_area_chat_box_chat_message_num = 0
# 聊天记录最多保留100条
scroll_area_chat_box_chat_message_max_num = 100


"""
初始化基本配置
"""
def init():
    """
    初始化基本配置
    """
    global config_path, config, common, audio

    common = Common()

    if getattr(sys, 'frozen', False):
        # 当前是打包后的可执行文件
        bundle_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        file_relative_path = bundle_dir.resolve()
    else:
        # 当前是源代码
        file_relative_path = Path(__file__).parent.resolve()

    # logger.info(file_relative_path)

    # 初始化文件夹
    def init_dir():
        # 创建日志文件夹
        log_dir = file_relative_path / 'log'
        # mkdir 方法的 parents=True 参数可以确保父目录的创建（如有必要），exist_ok=True 则避免在目录已存在时抛出异常。
        log_dir.mkdir(parents=True, exist_ok=True)

        # 创建音频输出文件夹
        audio_out_dir = file_relative_path / 'out'
        audio_out_dir.mkdir(parents=True, exist_ok=True)

    init_dir()
    logger.debug("项目相关文件夹初始化完成")

    # 配置文件路径
    config_path = file_relative_path / 'config.json'
    config_path = str(config_path)

    logger.debug("配置文件路径=" + str(config_path))

    # 实例化音频类
    audio = Audio(config_path, type=2)
    # 实例化配置类
    config = Config(config_path)

# 初始化基本配置
init()

# 将本地目录中的静态文件（如 CSS、JavaScript、图片等）暴露给 web 服务器，以便用户可以通过特定的 URL 访问这些文件。
if config.get("webui", "local_dir_to_endpoint", "enable"):
    for tmp in config.get("webui", "local_dir_to_endpoint", "config"):
        app.add_static_files(tmp['url_path'], tmp['local_dir'])

# 暗夜模式
# dark = ui.dark_mode()

"""
通用函数
"""
def textarea_data_change(data):
    """
    字符串数组数据格式转换
    """
    tmp_str = ""
    if data is not None:
        for tmp in data:
            tmp_str = tmp_str + tmp + "\n"
        
    return tmp_str



"""
                                                                                                    
                                               .@@@@@                           @@@@@.              
                                               .@@@@@                           @@@@@.              
        ]]]]]   .]]]]`   .]]]]`   ,]@@@@@\`    .@@@@@,/@@@\`   .]]]]]   ]]]]]`  ]]]]].              
        =@@@@^  =@@@@@`  =@@@@. =@@@@@@@@@@@\  .@@@@@@@@@@@@@  *@@@@@   @@@@@^  @@@@@.              
         =@@@@ ,@@@@@@@ .@@@@` =@@@@^   =@@@@^ .@@@@@`  =@@@@^ *@@@@@   @@@@@^  @@@@@.              
          @@@@^@@@@\@@@^=@@@^  @@@@@@@@@@@@@@@ .@@@@@   =@@@@@ *@@@@@   @@@@@^  @@@@@.              
          ,@@@@@@@^ \@@@@@@@   =@@@@^          .@@@@@.  =@@@@^ *@@@@@  .@@@@@^  @@@@@.              
           =@@@@@@  .@@@@@@.    \@@@@@]/@@@@@` .@@@@@@]/@@@@@. .@@@@@@@@@@@@@^  @@@@@.              
            \@@@@`   =@@@@^      ,\@@@@@@@@[   .@@@@^\@@@@@[    .\@@@@@[=@@@@^  @@@@@.    
            
"""
# 配置
webui_ip = config.get("webui", "ip")
webui_port = config.get("webui", "port")
webui_title = config.get("webui", "title")

# CSS
theme_choose = config.get("webui", "theme", "choose")
tab_panel_css = config.get("webui", "theme", "list", theme_choose, "tab_panel")
card_css = config.get("webui", "theme", "list", theme_choose, "card")
button_bottom_css = config.get("webui", "theme", "list", theme_choose, "button_bottom")
button_bottom_color = config.get("webui", "theme", "list", theme_choose, "button_bottom_color")
button_internal_css = config.get("webui", "theme", "list", theme_choose, "button_internal")
button_internal_color = config.get("webui", "theme", "list", theme_choose, "button_internal_color")
switch_internal_css = config.get("webui", "theme", "list", theme_choose, "switch_internal")
echart_css = config.get("webui", "theme", "list", theme_choose, "echart")

def goto_func_page():
    """
    跳转到功能页
    """
    global audio, my_subprocesses, config


    def start_programs():
        """根据配置启动所有程序。
        """
        global config

        name = "main"
        # 根据操作系统的不同，微调参数
        if common.detect_os() in ['Linux', 'MacOS']:
            process = subprocess.Popen(["python", f"main.py"], shell=False)
        else:
            process = subprocess.Popen(["python", f"main.py"], shell=True)
        my_subprocesses[name] = process

        logger.info(f"运行程序: {name}")


    def stop_program(name):
        """停止一个正在运行的程序及其所有子进程，兼容 Windows、Linux 和 macOS。

        Args:
            name (str): 要停止的程序的名称。
        """
        if name in my_subprocesses:
            pid = my_subprocesses[name].pid  # 获取进程ID
            logger.info(f"停止程序和它所有的子进程: {name} with PID {pid}")

            try:
                if os.name == 'nt':  # Windows
                    command = ["taskkill", "/F", "/T", "/PID", str(pid)]
                    subprocess.run(command, check=True)
                else:  # POSIX系统，如Linux和macOS
                    os.killpg(os.getpgid(pid), signal.SIGKILL)

                logger.info(f"程序 {name} 和 它所有的子进程都被终止.")
            except Exception as e:
                logger.error(f"终止程序 {name} 失败: {e}")

            del my_subprocesses[name]  # 从进程字典中移除
        else:
            logger.warning(f"程序 {name} 没有在运行.")

    def stop_programs():
        """根据配置停止所有程序。
        """
        global config

        stop_program("main")



    """

      =@@^      ,@@@^        .@@@. .....   =@@.      ]@\  ,]]]]]]]]]]]]]]].  .]]]]]]]]]]]]]]]]]]]]    ,]]]]]]]]]]]]]]]]]`    ,/. @@@^ /]  ,@@@.               
      =@@^ .@@@@@@@@@@@@@@^  /@@\]]@@@@@=@@@@@@@@@.  \@@@`=@@@@@@@@@@@@@@@.  .@@@@@@@@@@@@@@@@@@@@    =@@@@@@@@@@@@@@@@@^   .\@@^@@@\@@@`.@@@^                
    @@@@@@@^@@@@@@@@@@@@@@^ =@@@@@^ =@@\]]]/@@]]@@].  =@/`=@@^  .@@@  .@@@.  .@@@^    @@@^    =@@@             ,/@@@@/`     =@@@@@@@@@@@^=@@@@@@@@@.          
    @@@@@@@^@@@^@@\`   =@@^.@@@]]]`=@@^=@@@@@@@@@@@.]]]]` =@@^=@@@@@@@^@@@.  .@@@\]]]]@@@\]]]]/@@@   @@@\/@\..@@@@[./@/@@@. ,[[\@@@@/[[[\@@@`..@@@`           
      =@@^ ,]]]/@@@]]]]]]]].\@@@@@^@@@OO=@@@@@@@@@..@@@@^ =@@^]]]@@@]]`@@@.  .@@@@@@@@@@@@@@@@@@@@   @@@^=@@@^@@@^/@@@\@@@..]@@@@@@@@@@]@@@@^ .@@@.           
      =@@@@=@@@@@@@@@@@@@@@. =@@^ .OO@@@.[[\@@[[[[.  =@@^ =@@^@@@@@@@@^@@@.  .@@@^    @@@^    =@@@   @@@^ .`,]@@@^`,` =@@@. \@/.]@@@^,@@@@@@\ =@@^            
   .@@@@@@@. .@@@`   /@@/  .@@@@@@@,.=@@=@@@@@@@@@^  =@@^,=@@^=@@@@@@@.@@@.  .@@@\]]]]@@@\]]]]/@@@   @@@^]@@@@@@@@@@@]=@@@. ]]]@@@\]]]]] .=@@\@@@.            
    @@\@@^  .@@@\.  /@@@.    =@@^ =@\@@^.../@@.....  =@@@@=@@^=@@[[\@@.@@@.  .@@@@@@@@@@@@@@@@@@@@   @@@@@@/..@@@^,@@@@@@@. O@@@@@@@@@@@  .@@@@@^             
      =@@^   ,\@@@@@@@@.     =@@^/^\@@@`@@@@@@@@@@^  /@@@/@@@`=@@OO@@@.@@@.  =@@@`    @@@^    =@@@   @@@^  \@@@@@^   .=@@@. .@@@@\`/@@/    /@@@\.             
      =@@^    ,/@@@@@@@@]    =@@@@^/@@@@]` =@@.     .\@/.=@@@ =@@[[[[[.@@@.  /@@@     @@@^   ./@@@   @@@^.............=@@@.    O@@@@@@\`,/@@@@@@@@`           
    @@@@@^.@@@@@@@/..[@@@@/. ,@@`/@@@`[@@@@@@@@@@@@.    /@@@^      =@@@@@@. /@@@^     @@@^,@@@@@@^   @@@@@@@@@@@@@@@@@@@@@..\@@@@@[,\@@\@@@@` ,@@@^           
    ,[[[.  .O[[.        [`        ,/         ......       ,^       .[[[[`     ,`      .... [[[[`                      ,[[[. .[.         ,/.     .`

    """
    # 创建一个函数，用于运行外部程序
    def run_external_program(config_path="config.json", type="webui"):
        global running_flag

        if running_flag:
            if type == "webui":
                ui.notify(position="top", type="warning", message="运行中，请勿重复运行")
            return

        try:
            running_flag = True

            # 启动协同程序和主程序
            start_programs()

            if type == "webui":
                ui.notify(position="top", type="positive", message="程序开始运行")
            logger.info("程序开始运行")

            return {"code": 200, "msg": "程序开始运行"}
        except Exception as e:
            if type == "webui":
                ui.notify(position="top", type="negative", message=f"错误：{e}")
            logger.error(traceback.format_exc())
            running_flag = False

            return {"code": -1, "msg": f"运行失败！{e}"}


    # 定义一个函数，用于停止正在运行的程序
    def stop_external_program(type="webui"):
        global running_flag

        if running_flag:
            try:
                # 停止协同程序
                stop_programs()

                running_flag = False
                if type == "webui":
                    ui.notify(position="top", type="positive", message="程序已停止")
                logger.info("程序已停止")
            except Exception as e:
                if type == "webui":
                    ui.notify(position="top", type="negative", message=f"停止错误：{e}")
                logger.error(f"停止错误：{e}")

                return {"code": -1, "msg": f"重启失败！{e}"}


    # 开关灯


    # 重启
    def restart_application(type="webui"):
        try:
            # 先停止运行
            stop_external_program(type)

            logger.info(f"重启webui")
            if type == "webui":
                ui.notify(position="top", type="ongoing", message=f"重启中...")
            python = sys.executable
            os.execl(python, python, *sys.argv)  # Start a new instance of the application
        except Exception as e:
            logger.error(traceback.format_exc())
            return {"code": -1, "msg": f"重启失败！{e}"}
        
    # 恢复出厂配置
    def factory(src_path='config.json.bak', dst_path='config.json', type="webui"):
        # src_path = 'config.json.bak'
        # dst_path = 'config.json'

        try:
            with open(src_path, 'r', encoding="utf-8") as source:
                with open(dst_path, 'w', encoding="utf-8") as destination:
                    destination.write(source.read())
            logger.info("恢复出厂配置成功！")
            if type == "webui":
                ui.notify(position="top", type="positive", message=f"恢复出厂配置成功！")
            
            # 重启
            restart_application()

            return {"code": 200, "msg": "恢复出厂配置成功！"}
        except Exception as e:
            logger.error(f"恢复出厂配置失败！\n{e}")
            if type == "webui":
                ui.notify(position="top", type="negative", message=f"恢复出厂配置失败！\n{e}")
            
            return {"code": -1, "msg": f"恢复出厂配置失败！\n{e}"}

    # GSVI加载模型
    async def gsvi_set_init():
         
        try:
            # API_URL = urljoin(input_gsvi_ip_port.value, '/api')
            # resp_json = await common.send_async_request(API_URL, "GET", None , resp_data_type="json")
            # content = resp_json["message"]
            # logger.info(content)
            # ui.notify(position="top", type="positive", message=content)

            API_URL = urljoin(input_gsvi_ip_port.value, '/models')
            data_json = {
                "version": "v4"
            }
            resp_json = await common.send_async_request(API_URL, "POST", data_json , resp_data_type="json")
            logger.info(resp_json)
            ui.notify(position="top", type="positive", message=resp_json)

            model_names = list(resp_json["models"].keys())
            select_gsvi_models.options = model_names
            select_gsvi_models.update()

            def on_model_change():
                selected_model = select_gsvi_models.value
                if not selected_model:
                    return

                # 获取该模型下的语言字典，如 {"中文": ["默认"]}
                lang_dict = resp_json["models"][selected_model]

                # 提取语言列表，如 ["中文", "中 文"]
                langs = list(lang_dict.keys())

                # 更新语言下拉框
                select_gsvi_lang.options = langs
                select_gsvi_lang.update()

                # 同步更新默认值
                on_lang_change()

            # 绑定事件
            select_gsvi_models.on("update:modelValue", on_model_change)

            def on_lang_change():
                selected_model = select_gsvi_models.value
                selected_lang = select_gsvi_lang.value
                if not selected_model or not selected_lang:
                    return

                # 获取该语言下的默认值数组，如 ["默认"]
                defaults = resp_json["models"][selected_model].get(selected_lang, [])

                # 更新默认值下拉框
                select_gsvi_emotion.options = defaults
                select_gsvi_emotion.update()

            # 绑定事件
            select_gsvi_lang.on("update:modelValue", on_lang_change)
            
            if model_names:
                select_gsvi_models.set_value(model_names[0])  # 默认选中第一个模型
                on_model_change()  # 手动触发一次语言和默认值更新


            # API_URL = urljoin(input_gsvi_ip_port.value, '/v1/audio/speech')
            # data_json = {
            #     "model": "tts-v4",
            #     "input": "测试",
            #     "voice": ""
            # }
            # resp_json = await common.send_async_request(API_URL, "GET", data_json , resp_data_type="json")


        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'GSVI未知错误: {e}')
            ui.notify(position="top", type="negative", message=f'GSVI未知错误: {e}')


         
     

    # GPT-SoVITS加载模型
    async def gpt_sovits_set_model():
        try:
            if select_gpt_sovits_type.value == "v2_api_0821":
                async def set_gpt_weights():
                    try:

                        API_URL = urljoin(input_gpt_sovits_api_ip_port.value, '/set_gpt_weights?weights_path=' + input_gpt_sovits_gpt_model_path.value)
                        resp_json = await common.send_async_request(API_URL, "GET", None, resp_data_type="json")

                        if resp_json is None:
                            content = f"gpt_weights：{input_gpt_sovits_gpt_model_path.value} 加载失败，请查看双方日志排查问题"
                            logger.error(content)
                            return False
                        else:
                            if resp_json["message"] == "success":
                                content = f"gpt_weights：{input_gpt_sovits_gpt_model_path.value} 加载成功"
                                logger.info(content)
                            else:
                                content = f"gpt_weights：{input_gpt_sovits_gpt_model_path.value} 加载失败，请查看双方日志排查问题"
                                logger.error(content)
                                return False
                        
                        return True
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        logger.error(f'gpt_sovits未知错误: {e}')
                        return False

                async def set_sovits_weights():
                    try:

                        API_URL = urljoin(input_gpt_sovits_api_ip_port.value, '/set_sovits_weights?weights_path=' + input_gpt_sovits_sovits_model_path.value)

                        resp_json = await common.send_async_request(API_URL, "GET", None, resp_data_type="json")

                        if resp_json is None:
                            content = f"sovits_weights：{input_gpt_sovits_sovits_model_path.value} 加载失败，请查看双方日志排查问题"
                            logger.error(content)
                            return False
                        else:
                            if resp_json["message"] == "success":
                                content = f"sovits_weights：{input_gpt_sovits_sovits_model_path.value} 加载成功"
                                logger.info(content)
                            else:
                                content = f"sovits_weights：{input_gpt_sovits_sovits_model_path.value} 加载失败，请查看双方日志排查问题"
                                logger.error(content)
                                return False
                        
                        return True
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        logger.error(f'sovits_weights未知错误: {e}')
                        return False
            
                if await set_gpt_weights() and await set_sovits_weights():
                    content = "gpt_sovits模型加载成功"
                    logger.info(content)
                    ui.notify(position="top", type="positive", message=content)
                else:
                    content = "gpt_sovits模型加载失败，请查看双方日志排查问题"
                    logger.error(content)
                    ui.notify(position="top", type="negative", message=content)
            else:
                API_URL = urljoin(input_gpt_sovits_api_ip_port.value, '/set_model')

                data_json = {
                    "gpt_model_path": input_gpt_sovits_gpt_model_path.value,
                    "sovits_model_path": input_gpt_sovits_sovits_model_path.value
                }
                
                resp_data = await common.send_async_request(API_URL, "POST", data_json, resp_data_type="content")

                if resp_data is None:
                    content = "gpt_sovits加载模型失败，请查看双方日志排查问题"
                    logger.error(content)
                    ui.notify(position="top", type="negative", message=content)
                else:
                    content = "gpt_sovits加载模型成功"
                    logger.info(content)
                    ui.notify(position="top", type="positive", message=content)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'gpt_sovits未知错误: {e}')
            ui.notify(position="top", type="negative", message=f'gpt_sovits未知错误: {e}')



    # 页面滑到顶部
    def scroll_to_top():
        # 这段JavaScript代码将页面滚动到顶部
        ui.run_javascript("window.scrollTo(0, 0);")   

    # 显示聊天数据的滚动框
    scroll_area_chat_box = None

    # 处理数据 显示聊天记录
    def data_handle_show_chat_log(data_json):
        global scroll_area_chat_box_chat_message_num

        if data_json["type"] == "llm":
            if data_json["data"]["content_type"] == "question":
                name = data_json["data"]['username']
                if 'user_face' in data_json["data"]:
                    # 由于直接请求b站头像返回403 所以暂时还是用默认头像
                    # avatar = data_json["data"]['user_face']
                    avatar = 'https://robohash.org/ui'
                else:
                    avatar = 'https://robohash.org/ui'
            else:
                name = data_json["data"]['type']
                avatar = "http://127.0.0.1:8081/favicon.ico"

            with scroll_area_chat_box:
                ui.chat_message(data_json["data"]["content"],
                    name=name,
                    stamp=data_json["data"]["timestamp"],
                    avatar=avatar
                )

                scroll_area_chat_box_chat_message_num += 1

            if scroll_area_chat_box_chat_message_num > scroll_area_chat_box_chat_message_max_num:
                scroll_area_chat_box.remove(0)

            scroll_area_chat_box.scroll_to(percent=1, duration=0.2)

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
    
    

    from starlette.requests import Request
    from utils.models import SendMessage, CommonResult, SysCmdMessage, SetConfigMessage

    """
    配置config

        config_path (str): 配置文件路径
        data (dict): 传入的json

    return:
        {"code": 200, "message": "成功"}
    """
    @app.post('/set_config')
    async def set_config(msg: SetConfigMessage):
        global config

        try:
            data_json = msg.dict()
            logger.info(f'set_config接口 收到数据：{data_json}')

            config_data = None

            try:
                with open(data_json["config_path"], 'r', encoding="utf-8") as config_file:
                    config_data = json.load(config_file)
            except Exception as e:
                logger.error(f"无法读取配置文件！\n{e}")
                return CommonResult(code=-1, message=f"无法读取配置文件！{e}")
            
            # 合并字典
            config_data.update(data_json["data"])

            # 写入配置到配置文件
            try:
                with open(data_json["config_path"], 'w', encoding="utf-8") as config_file:
                    json.dump(config_data, config_file, indent=2, ensure_ascii=False)
                    config_file.flush()  # 刷新缓冲区，确保写入立即生效

                logger.info("配置数据已成功写入文件！")

                return CommonResult(code=200, message="配置数据已成功写入文件！")
            except Exception as e:
                logger.error(f"无法写入配置文件！\n{str(e)}")
                return CommonResult(code=-1, message=f"无法写入配置文件！{e}")
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"{data_json['type']}执行失败！{e}")

    """
    系统命令
        type 命令类型（run/stop/restart/factory）
        data 传入的json

    data_json = {
        "type": "命令名",
        "data": {
            "key": "value"
        }
    }

    return:
        {"code": 200, "message": "成功"}
        {"code": -1, "message": "失败"}
    """
    @app.post('/sys_cmd')
    async def sys_cmd(msg: SysCmdMessage):
        try:
            data_json = msg.dict()
            logger.info(f'sys_cmd接口 收到数据：{data_json}')
            logger.info(f"开始执行 {data_json['type']}命令...")

            resp_json = {}

            if data_json['type'] == 'run':
                """
                {
                    "type": "run",
                    "data": {
                        "config_path": "config.json"
                    }
                }
                """
                # 运行
                resp_json = run_external_program(data_json['data']['config_path'], type="api")
            elif data_json['type'] =='stop':
                """
                {
                    "type": "stop",
                    "data": {
                        "config_path": "config.json"
                    }
                }
                """
                # 停止
                resp_json = stop_external_program(type="api")
            elif data_json['type'] =='restart':
                """
                {
                    "type": "restart",
                    "api_type": "webui",
                    "data": {
                        "config_path": "config.json"
                    }
                }
                """
                # 重启
                resp_json = restart_application(type=data_json['api_type'])
            elif data_json['type'] =='factory':
                """
                {
                    "type": "factory",
                    "api_type": "webui",
                    "data": {
                        "src_path": "config.json.bak",
                        "dst_path": "config.json"
                    }
                }
                """
                # 恢复出厂
                resp_json = factory(data_json['data']['src_path'], data_json['data']['dst_path'], type="api")

            return resp_json
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"{data_json['type']}执行失败！{e}")

    """
    发送数据
        type 数据类型（comment/gift/entrance/reread/tuning/...）
        key  根据数据类型自行适配

    data_json = {
        "type": "数据类型",
        "key": "value"
    }

    return:
        {"code": 200, "message": "成功"}
        {"code": -1, "message": "失败"}
    """
    @app.post('/send')
    async def send(msg: SendMessage):
        global config

        try:
            data_json = msg.dict()
            logger.info(f'WEBUI API send接口收到数据：{data_json}')

            main_api_ip = "127.0.0.1" if config.get("api_ip") == "0.0.0.0" else config.get("api_ip")
            resp_json = await common.send_async_request(f'http://{main_api_ip}:{config.get("api_port")}/send', "POST", data_json)

            return resp_json
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"发送数据失败！{e}")



    """
    数据回调
        data 传入的json

    data_json = {
        "type": "数据类型（llm）",
        "data": {
            "type": "LLM类型",
            "username": "用户名",
            "content_type": "内容的类型（question/answer）",
            "content": "回复内容",
            "timestamp": "时间戳"
        }
    }

    return:
        {"code": 200, "message": "成功"}
        {"code": -1, "message": "失败"}
    """
    @app.post('/callback')
    async def callback(request: Request):
        try:
            data_json = await request.json()
            logger.info(f'WEBUI API callback接口收到数据：{data_json}')

            data_handle_show_chat_log(data_json)

            return {"code": 200, "message": "成功"}
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"失败！{e}")


    """
    TTS合成，获取合成的音频文件路径
        data 传入的json

    例如：
    data_json = {
        "type": "reread",
        "tts_type": "gpt_sovits",
        "data": {
            "type": "api",
            "api_ip_port": "http://127.0.0.1:9880",
            "ref_audio_path": "F:\\GPT-SoVITS\\raws\\ikaros\\21.wav",
            "prompt_text": "マスター、どうりょくろか、いいえ、なんでもありません",
            "prompt_language": "日文",
            "language": "自动识别",
            "cut": "凑四句一切",
            "gpt_model_path": "F:\\GPT-SoVITS\\GPT_weights\\ikaros-e15.ckpt",
            "sovits_model_path": "F:\\GPT-SoVITS\\SoVITS_weights\\ikaros_e8_s280.pth",
            "webtts": {
                "api_ip_port": "http://127.0.0.1:8080",
                "spk": "sanyueqi",
                "lang": "zh",
                "speed": "1.0",
                "emotion": "正常"
            }
        },
        "username": "主人",
        "content": "你好，这就是需要合成的文本内容"
    }

    return:
        {
            "code": 200,
            "message": "成功",
            "data": {
                "type": "reread",
                "tts_type": "gpt_sovits",
                "data": {
                    "type": "api",
                    "api_ip_port": "http://127.0.0.1:9880",
                    "ref_audio_path": "F:\\\\GPT-SoVITS\\\\raws\\\\ikaros\\\\21.wav",
                    "prompt_text": "マスター、どうりょくろか、いいえ、なんでもありません",
                    "prompt_language": "日文",
                    "language": "自动识别",
                    "cut": "凑四句一切",
                    "gpt_model_path": "F:\\GPT-SoVITS\\GPT_weights\\ikaros-e15.ckpt",
                    "sovits_model_path": "F:\\GPT-SoVITS\\SoVITS_weights\\ikaros_e8_s280.pth",
                    "webtts": {
                        "api_ip_port": "http://127.0.0.1:8080",
                        "spk": "sanyueqi",
                        "lang": "zh",
                        "speed": "1.0",
                        "emotion": "正常"
                    }
                },
                "username": "主人",
                "content": "你好，这就是需要合成的文本内容",
                "result": {
                    "code": 200,
                    "msg": "合成成功",
                    "audio_path": "E:\\GitHub_pro\\AI-Vtuber\\out\\gpt_sovits_4.wav"
                }
            }
        }

        {"code": -1, "message": "失败"}
    """
    @app.post('/tts')
    async def tts(request: Request):
        try:
            data_json = await request.json()
            logger.info(f'WEBUI API tts接口收到数据：{data_json}')

            resp_json = await audio.tts_handle(data_json)

            return {"code": 200, "message": "成功", "data": resp_json}
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"失败！{e}")


    """
    LLM推理，获取推理结果
        data 传入的json

    例如：type就是聊天类型实际对应的值
    data_json = {
        "type": "chatgpt",
        "username": "用户名",
        "content": "你好"
    }

    return:
        {
            "code": 200,
            "message": "成功",
            "data": {
                "content": "你好，这是LLM回复的内容"
            }
        }

        {"code": -1, "message": "失败"}
    """
    @app.post('/llm')
    async def llm(request: Request):
        try:
            data_json = await request.json()
            logger.info(f'WEBUI API llm接口 收到数据：{data_json}')

            main_api_ip = "127.0.0.1" if config.get("api_ip") == "0.0.0.0" else config.get("api_ip")
            resp_json = await common.send_async_request(f'http://{main_api_ip}:{config.get("api_port")}/llm', "POST", data_json, "json", timeout=60)
            if resp_json:
                return resp_json
            
            return CommonResult(code=-1, message="失败！")
        except Exception as e:
            logger.error(traceback.format_exc())
            return CommonResult(code=-1, message=f"失败！{e}")

    # 获取系统信息接口
    @app.get("/get_sys_info")
    async def get_sys_info():
        try:
            # logger.info(f'WEBUI API get_sys_info接口 收到请求')

            main_api_ip = "127.0.0.1" if config.get("api_ip") == "0.0.0.0" else config.get("api_ip")
            resp_json = await common.send_async_request(f'http://{main_api_ip}:{config.get("api_port")}/get_sys_info', "GET", None, "json", timeout=60)
            if resp_json:
                return resp_json
            return CommonResult(code=-1, message="失败！")
        except Exception as e:
            logger.error(f"get_sys_info处理失败！{e}")
            return CommonResult(code=-1, message=f"get_sys_info处理失败！{e}")


    # fish speech 获取说话人数据
    async def fish_speech_web_get_ref_data(speaker):
        if speaker == "":
            logger.info("说话人不能为空喵~")
            ui.notify(position="top", type="warning", message="说话人不能为空喵~")
            return

        from utils.audio_handle.my_tts import MY_TTS
        
        my_tts = MY_TTS(config_path)
        data_json = await my_tts.fish_speech_web_get_ref_data(speaker)
        if data_json is None:
            ui.notify(position="top", type="negative", message="获取数据失败，请查看日志定位问题")
            return
        
       
        ui.notify(position="top", type="positive", message="获取数据成功，已自动填入输入框")

        
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


    



    
    # 自定义命令-增加
    def custom_cmd_add():
        data_len = len(custom_cmd_config_var)

        tmp_config = {
            "keywords": [],
            "similarity": 1,
            "api_url": "",
            "api_type": "",
            "resp_data_type": "",
            "data_analysis": "",
            "resp_template": ""
        }

        with custom_cmd_config_card.style(card_css):
            with ui.row():
                custom_cmd_config_var[str(data_len)] = ui.textarea(label=f"关键词#{int(data_len / 7) + 1}", value=textarea_data_change(tmp_config["keywords"]), placeholder='此处输入触发的关键词，多个请以换行分隔').style("width:200px;")
                custom_cmd_config_var[str(data_len + 1)] = ui.input(label=f"相似度#{int(data_len / 7) + 1}", value=tmp_config["similarity"], placeholder='关键词与用户输入的相似度，默认1即100%').style("width:100px;")
                custom_cmd_config_var[str(data_len + 2)] = ui.textarea(label=f"API URL#{int(data_len / 7) + 1}", value=tmp_config["api_url"], placeholder='发送HTTP请求的API链接', validation={'请输入正确格式的URL': lambda value: common.is_url_check(value),}).style("width:300px;")
                custom_cmd_config_var[str(data_len + 3)] = ui.select(label=f"API类型#{int(data_len / 7) + 1}", value=tmp_config["api_type"], options={"GET": "GET"}).style("width:100px;")
                custom_cmd_config_var[str(data_len + 4)] = ui.select(label=f"请求返回数据类型#{int(data_len / 7) + 1}", value=tmp_config["resp_data_type"], options={"json": "json", "content": "content"}).style("width:150px;")
                custom_cmd_config_var[str(data_len + 5)] = ui.textarea(label=f"数据解析（eval执行）#{int(data_len / 7) + 1}", value=tmp_config["data_analysis"], placeholder='数据解析，请不要随意修改resp变量，会被用于最后返回数据内容的解析').style("width:200px;")
                custom_cmd_config_var[str(data_len + 6)] = ui.textarea(label=f"返回内容模板#{int(data_len / 7) + 1}", value=tmp_config["resp_template"], placeholder='请不要随意删除data变量，支持动态变量，最终会合并成完成内容进行音频合成').style("width:300px;")


    # 自定义命令-删除
    def custom_cmd_del(index):
        try:
            custom_cmd_config_card.remove(int(index) - 1)
            # 删除操作
            keys_to_delete = [str(7 * (int(index) - 1) + i) for i in range(7)]
            for key in keys_to_delete:
                if key in custom_cmd_config_var:
                    del custom_cmd_config_var[key]

            # 重新编号剩余的键
            updates = {}
            for key in sorted(custom_cmd_config_var.keys(), key=int):
                new_key = str(int(key) - 7 if int(key) > int(keys_to_delete[-1]) else key)
                updates[new_key] = custom_cmd_config_var[key]

            # 应用更新
            custom_cmd_config_var.clear()
            custom_cmd_config_var.update(updates)
        except Exception as e:
            ui.notify(position="top", type="negative", message=f"错误，索引值配置有误：{e}")
            logger.error(traceback.format_exc())

    """
    串口
    """
    # 
    


    """
    添加本地路径到URL路径
    """
    # -增加
    def webui_local_dir_to_endpoint_add():
        data_len = len(webui_local_dir_to_endpoint_config_var)
        tmp_config = {
            "url_path": "",
            "local_dir": "",
        }

        with webui_local_dir_to_endpoint_config_card.style(card_css):
            with ui.row():
                webui_local_dir_to_endpoint_config_var[str(data_len)] = ui.input(label=f"URL路径#{int(data_len / 2) + 1}", value=tmp_config["url_path"], placeholder='以斜杠（"/"）开始的字符串，它标识了应该为客户端提供文件的URL路径').style("width:300px;")
                webui_local_dir_to_endpoint_config_var[str(data_len + 1)] = ui.input(label=f"本地文件夹路径#{int(data_len / 2) + 1}", value=tmp_config["local_dir"], placeholder='本地文件夹路径，建议相对路径，最好是项目内部的路径').style("width:300px;")


    # -删除
    def webui_local_dir_to_endpoint_del(index):
        try:
            webui_local_dir_to_endpoint_config_card.remove(int(index) - 1)
            # 删除操作
            keys_to_delete = [str(2 * (int(index) - 1) + i) for i in range(2)]
            for key in keys_to_delete:
                if key in webui_local_dir_to_endpoint_config_var:
                    del webui_local_dir_to_endpoint_config_var[key]

            # 重新编号剩余的键
            updates = {}
            for key in sorted(webui_local_dir_to_endpoint_config_var.keys(), key=int):
                new_key = str(int(key) - 2 if int(key) > int(keys_to_delete[-1]) else key)
                updates[new_key] = webui_local_dir_to_endpoint_config_var[key]

            # 应用更新
            webui_local_dir_to_endpoint_config_var.clear()
            webui_local_dir_to_endpoint_config_var.update(updates)
        except Exception as e:
            ui.notify(position="top", type="negative", message=f"错误，索引值配置有误：{e}")
            logger.error(traceback.format_exc())


    # 配置模板保存
    def config_template_save(file_path: str):
        try:
            with open(config_path, 'r', encoding="utf-8") as config_file:
                config_data = json.load(config_file)

            config_data = webui_config_to_dict(config_data)

            # 将JSON数据保存到文件中
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(config_data, file, indent=2, ensure_ascii=False)
                file.flush()  # 刷新缓冲区，确保写入立即生效

            logger.info("配置模板保存成功！")
            ui.notify(position="top", type="positive", message=f"配置模板保存成功！")

            return True
        except Exception as e:
            logger.error(f"配置模板保存失败！\n{e}")
            ui.notify(position="top", type="negative", message=f"配置模板保存失败！{e}")
            return False


    # 配置模板加载
    def config_template_load(file_path: str):
        try:
            with open(file_path, 'r', encoding="utf-8") as config_file:
                config_data = json.load(config_file)

            # 将JSON数据保存到文件中
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(config_data, file, indent=2, ensure_ascii=False)
                file.flush()  # 刷新缓冲区，确保写入立即生效

            logger.info("配置模板加载成功！重启后读取！想反悔就直接保存下当前配置，然后再重启！！！")
            ui.notify(position="top", type="positive", message=f"配置模板加载成功！重启后读取！想反悔就直接保存下当前配置，然后再重启！！！")
            
            return True
        except Exception as e:
            logger.error(f"配置模板读取失败！\n{e}")
            ui.notify(position="top", type="negative", message=f"配置模板读取失败！{e}")
            return False


    """
    配置操作
    """
    # 配置检查
    def check_config():
        try:
            # 通用配置 页面 配置正确性校验
            if select_platform.value == 'bilibili2' and select_bilibili_login_type.value == 'cookie' and input_bilibili_cookie.value == '':
                ui.notify(position="top", type="warning", message="请先前往 通用配置-哔哩哔哩，填写B站cookie")
                return False
            elif select_platform.value == 'bilibili2' and select_bilibili_login_type.value == 'open_live' and \
                (input_bilibili_open_live_ACCESS_KEY_ID.value == '' or input_bilibili_open_live_ACCESS_KEY_SECRET.value == '' or \
                input_bilibili_open_live_APP_ID.value == '' or input_bilibili_open_live_ROOM_OWNER_AUTH_CODE.value == ''):
                ui.notify(position="top", type="warning", message="请先前往 通用配置-哔哩哔哩，填写开放平台配置")
                return False


            """
            针对配置情况进行提示
            """
            tip_config = f'平台：{platform_options[select_platform.value]} | ' +\
                f'语音合成：{audio_synthesis_type_options[select_audio_synthesis_type.value]} | ' 
            ui.notify(position="top", type="info", message=tip_config)

            # 检测平台配置，进行提示
            if select_platform.value == "dy":
                ui.notify(position="top", type="warning", message="对接抖音平台时，请先开启抖音弹幕监听程序！直播间号不需要填写")
            elif select_platform.value == "bilibili":
                ui.notify(position="top", type="info", message="哔哩哔哩1 监听不是很稳定，推荐使用 哔哩哔哩2")
            elif select_platform.value == "bilibili2":
                if select_bilibili_login_type.value == "不登录":
                    ui.notify(position="top", type="warning", message="哔哩哔哩2 在不登录的情况下，无法获取用户完整的用户名")

            return True
        except Exception as e:
            ui.notify(position="top", type="negative", message=f"配置错误：{e}")
            return False

    """
    
.................................................................................................................................................................
.................................................................................................................................................................
.................................................................................................................................................................
.................................................................................................................................................................
.............................................................................................................:**.................................................
........+++..........-++:....:++:...*##############:%%%%%%%%%#.....%%%%%%%%%%%%%%%%%%%%%%%.....%@#...........-@%..........+%%%%%%%%%%%%%+-----------:............
........%@#..........=@@=....-@@=....::::%#:=@+::::.........%%.....%%.....%%.....%#.....%%......+@@*..#%%%%%%%@@%%%%%%%%....=@#.....%@-.*%@#######%@=............
........%@#..........=@@=....-@@=........%*.-@+.............%%.....%@%%%%%@@%%%%%@@%%%%%@%........%%:........-@%............=@#.....%@-..#@-......#@-............
........%@#..........=@@=....-@@=....%%%%@@%%@%%%%=.........%%.....::........#%=........::...................=@%:...........=@%#####%@-..=@=.....-%%.............
........%@#..........=@@=....-@@=....%%..%*.-@+.=@=.........%%...%%%%%%%%%%%%@@%%%%%%%%%%%%*.:-----..#%%%%%%%%%%%%%%%%%@-...=@#-----%@-..:%#.....*@=.............
........%@#..........=@@=....-@@=....%%.:%*.-@+.=@=.-%@@@@@@@%...............%@=.............+##%@%.....=%%+:..=@#....#%:...=@#.....%@-...#@-....%%..............
........%@#..........=@@=....-@@=....%%.+@=.-@+.=@=.=@+.....##.......@%***************#@+.......=@%....-..:*%#.=@#....+*....=@#-----%@-...-%#...#@=..............
........%@#..........=@@=....-@@=....%%+@#...*%%%@=.=@+..............@#===============*@+.......=@%...-#@%*:...+@*..........=@%*****%@-....*@=.=%*...............
........#@%..........+@@:....-@@=....%%-*.......=@=.=@+..............@#-::::::::::::::+@+.......=@%......:**...*@+..........=@#.....%@-.....%@#%%................
........*@@=........:%@#.....-@@=....%@%%%%%%%%%%@=.=@+......-*:.....@%%%%%%%%%%%%%%%%%@+.......=@%.:%@@@@@@@@@@@@@@@@@@%...=@#.....%@++*=...%@#.................
.........*@@%-.....*%@%......-@@=....%%.........=@=.-@+......+@=.....@*...............=@+.......=@%..:........%@*.........+#%@%%%@@@@@#+-..:%@%@%................
..........:%%@@@@@@%%-.......-@@=....%%.........=@=.-@+......%@-.....@%%%%%%%%%%%%%%%%%@+.......=@%#@%:....:#@%*%@%*......+*=:......%@-...#@%..:%@*..............
.....................................%@@@@@@@@@@@@=.:%@#+==+%@%.....:@#...............=@*.......#@@#-..:+%@@%-....=#@@#-............%@--%@%-.....+%@%=...........
.....................................%%.........=%=...=*****+:..-***************************-...-+...#@%#+:..........-#%:...........%@=%#:.........+#............
.................................................................................................................................................................
.................................................................................................................................................................
.................................................................................................................................................................
.................................................................................................................................................................

    """

    # 读取webui配置到dict变量
    def webui_config_to_dict(config_data):
        """读取webui配置到dict变量

        Args:
            config_data (dict): 从本地配置文件读取的dict数据
        """

        def common_textarea_handle(content):
            """通用的textEdit 多行文本内容处理

            Args:
                content (str): 原始多行文本内容

            Returns:
                _type_: 处理好的多行文本内容
            """
            ret = [token.strip() for token in content.split("\n") if token.strip()]
            return ret

        # 类型处理函数
        def handle_int(value):
            if value.value == '' or value.value is None:
                return 0
            return int(value.value)

        def handle_float(value):
            if value.value == '' or value.value is None:
                return 0
            return round(float(value.value), 2)

        def handle_string(value):
            return str(value.value)

        def handle_bool(value):
            return bool(value.value)

        def handle_textarea(value):
            return common_textarea_handle(value.value)

        # 处理器映射
        type_handlers = {
            'int': handle_int,
            'float': handle_float,
            'str': handle_string,
            'bool': handle_bool,
            'textarea': handle_textarea,
        }

        def update_nested_dict(target, keys, value):
            """递归更新嵌套字典"""
            if len(keys) == 1:
                target[keys[0]] = value
                return
            if keys[0] not in target:
                target[keys[0]] = {}
            update_nested_dict(target[keys[0]], keys[1:], value)

        def process_config_mapping(config_data, mapping, show_card_check=None):
            """处理配置映射，支持不同层级的嵌套"""
            def recurse_mapping(current_mapping, current_path=[]):
                for key, value in current_mapping.items():
                    new_path = current_path + [key]
                    if isinstance(value, dict):
                        recurse_mapping(value, new_path)
                    else:
                        component, type_name = value
                        handler = type_handlers[type_name]
                        processed_value = handler(component)
                        update_nested_dict(config_data, new_path, processed_value)

            recurse_mapping(mapping)
            return config_data


        def update_config(config_mapping, config, config_data, type="common_config"):
            # 处理常规配置
            for section, section_mapping in config_mapping.items():
                if type is not None:
                    if config.get("webui", "show_card", type, section):
                        if section not in config_data:
                            config_data[section] = {}
                        
                        process_config_mapping(config_data[section], section_mapping)
                else:
                    if section not in config_data:
                        config_data[section] = {}
                    
                    process_config_mapping(config_data[section], section_mapping)

            return config_data



        try:
            """
            通用配置
            """
            if True:
                config_data["platform"] = select_platform.value
                config_data["room_display_id"] = input_room_display_id.value
                config_data["need_lang"] = select_need_lang.value
                config_data["before_prompt"] = input_before_prompt.value
                config_data["after_prompt"] = input_after_prompt.value
                config_data["audio_synthesis_type"] = select_audio_synthesis_type.value

                config_mapping = {
                    "comment_template": {
                        "enable": (switch_comment_template_enable, 'bool'),
                        "copywriting": (input_comment_template_copywriting, 'str'),
                    },
                    "reply_template": {
                        "enable": (switch_reply_template_enable, 'bool'),
                        "username_max_len": (input_reply_template_username_max_len, 'int'),
                        "copywriting": (textarea_reply_template_copywriting, 'textarea'),
                    },
                    "bilibili": {
                        "login_type": (select_bilibili_login_type, 'str'),
                        "cookie": (input_bilibili_cookie, 'str'),
                        "ac_time_value": (input_bilibili_ac_time_value, 'str'),
                        "username": (input_bilibili_username, 'str'),
                        "password": (input_bilibili_password, 'str'),
                        "open_live": {
                            "ACCESS_KEY_ID": (input_bilibili_open_live_ACCESS_KEY_ID, 'str'),
                            "ACCESS_KEY_SECRET": (input_bilibili_open_live_ACCESS_KEY_SECRET, 'str'),
                            "APP_ID": (input_bilibili_open_live_APP_ID, 'int'),
                            "ROOM_OWNER_AUTH_CODE": (input_bilibili_open_live_ROOM_OWNER_AUTH_CODE, 'str'),
                        },
                    },
                }
                config_data = update_config(config_mapping, config, config_data, None)
                
                config_mapping = {}
                # 日志
                if config.get("webui", "show_card", "common_config", "log"):
                    config_data["comment_log_type"] = select_comment_log_type.value
                    config_data["captions"]["enable"] = switch_captions_enable.value
                    config_data["captions"]["file_path"] = input_captions_file_path.value
                    config_data["captions"]["raw_file_path"] = input_captions_raw_file_path.value

            
                # 音频播放
                if config.get("webui", "show_card", "common_config", "play_audio"):
                    # audio_player
                    config_data["audio_player"]["api_ip_port"] = input_audio_player_api_ip_port.value

                    config_mapping = {
                        "play_audio": {
                            "enable": (switch_play_audio_enable, 'bool'),
                            "text_split_enable": (switch_play_audio_text_split_enable, 'bool'),
                            "info_to_callback": (switch_play_audio_info_to_callback, 'bool'),
                            "interval_num_min": (input_play_audio_interval_num_min, 'int'),
                            "interval_num_max": (input_play_audio_interval_num_max, 'int'),
                            "normal_interval_min": (input_play_audio_normal_interval_min, 'float'),
                            "normal_interval_max": (input_play_audio_normal_interval_max, 'float'),
                            "out_path": (input_play_audio_out_path,'str'),
                            "player": (select_play_audio_player,'str'),
                        }
                    }

                if config.get("webui", "show_card", "common_config", "read_comment"):
                    config_mapping["read_comment"] = {
                        "enable": (switch_read_comment_enable, 'bool'),
                        "read_username_enable": (switch_read_comment_read_username_enable, 'bool'),
                        "username_max_len": (input_read_comment_username_max_len, 'int'),
                        "voice_change": (switch_read_comment_voice_change, 'bool'),
                        "read_username_copywriting": (textarea_read_comment_read_username_copywriting, 'textarea'),
                        "periodic_trigger": {
                            "enable": (switch_read_comment_periodic_trigger_enable, 'bool'),
                            "periodic_time_min": (input_read_comment_periodic_trigger_periodic_time_min, 'int'),
                            "periodic_time_max": (input_read_comment_periodic_trigger_periodic_time_max, 'int'),
                            "trigger_num_min": (input_read_comment_periodic_trigger_trigger_num_min, 'int'),
                            "trigger_num_max": (input_read_comment_periodic_trigger_trigger_num_max, 'int'),
                        },
                    }

                if config.get("webui", "show_card", "common_config", "filter"):
                    config_mapping["filter"] = {
                      
                        "comment_forget_duration": (input_filter_comment_forget_duration, 'float'),
                        "comment_forget_reserve_num": (input_filter_comment_forget_reserve_num, 'int'),
                        "gift_forget_duration": (input_filter_gift_forget_duration, 'float'),
                        "gift_forget_reserve_num": (input_filter_gift_forget_reserve_num, 'int'),
                        "schedule_forget_duration": (input_filter_schedule_forget_duration, 'float'),
                        "schedule_forget_reserve_num": (input_filter_schedule_forget_reserve_num, 'int'),
                        "limited_time_deduplication": {
                            "enable": (switch_filter_limited_time_deduplication_enable, 'bool'),
                            "comment": (input_filter_limited_time_deduplication_comment, 'int'),
                            "gift": (input_filter_limited_time_deduplication_gift, 'int'),
                            "entrance": (input_filter_limited_time_deduplication_entrance, 'int'),
                        },
                        "message_queue_max_len": (input_filter_message_queue_max_len, 'int'),
                        "voice_tmp_path_queue_max_len": (input_filter_voice_tmp_path_queue_max_len, 'int'),
                        "voice_tmp_path_queue_min_start_play": (input_filter_voice_tmp_path_queue_min_start_play, 'int'),
                        "priority_mapping": {
                            
                            "comment": (input_filter_priority_mapping_comment, 'int'),
                            "read_comment": (input_filter_priority_mapping_read_comment, 'int'),
                            "entrance": (input_filter_priority_mapping_entrance, 'int'),
                            "gift": (input_filter_priority_mapping_gift, 'int'),
                            "follow": (input_filter_priority_mapping_follow, 'int'),
                            "copywriting": (input_filter_priority_mapping_copywriting, 'int'),
                            
                        },
                    }

                if config.get("webui", "show_card", "common_config", "thanks"):
                    config_mapping["thanks"] = {
                        "username_max_len": (input_thanks_username_max_len, 'int'),
                        "entrance_enable": (switch_thanks_entrance_enable, 'bool'),
                        "entrance_random": (switch_thanks_entrance_random, 'bool'),
                        "entrance_copy": (textarea_thanks_entrance_copy, 'textarea'),
                        "entrance": {
                            "periodic_trigger": {
                                "enable": (switch_thanks_entrance_periodic_trigger_enable, 'bool'),
                                "periodic_time_min": (input_thanks_entrance_periodic_trigger_periodic_time_min, 'int'),
                                "periodic_time_max": (input_thanks_entrance_periodic_trigger_periodic_time_max, 'int'),
                                "trigger_num_min": (input_thanks_entrance_periodic_trigger_trigger_num_min, 'int'),
                                "trigger_num_max": (input_thanks_entrance_periodic_trigger_trigger_num_max, 'int'),
                            }
                        },
                        "gift_enable": (switch_thanks_gift_enable, 'bool'),
                        "gift_random": (switch_thanks_gift_random, 'bool'),
                        "gift_copy": (textarea_thanks_gift_copy, 'textarea'),
                        "gift": {
                            "periodic_trigger": {
                                "enable": (switch_thanks_gift_periodic_trigger_enable, 'bool'),
                                "periodic_time_min": (input_thanks_gift_periodic_trigger_periodic_time_min, 'int'),
                                "periodic_time_max": (input_thanks_gift_periodic_trigger_periodic_time_max, 'int'),
                                "trigger_num_min": (input_thanks_gift_periodic_trigger_trigger_num_min, 'int'),
                                "trigger_num_max": (input_thanks_gift_periodic_trigger_trigger_num_max, 'int'),
                            }
                        },
                        "follow_enable": (switch_thanks_follow_enable, 'bool'),
                        "follow_random": (switch_thanks_follow_random, 'bool'),
                        "follow_copy": (textarea_thanks_follow_copy, 'textarea'),
                        "follow": {
                            "periodic_trigger": {
                                "enable": (switch_thanks_follow_periodic_trigger_enable, 'bool'),
                                "periodic_time_min": (input_thanks_follow_periodic_trigger_periodic_time_min, 'int'),
                                "periodic_time_max": (input_thanks_follow_periodic_trigger_periodic_time_max, 'int'),
                                "trigger_num_min": (input_thanks_follow_periodic_trigger_trigger_num_min, 'int'),
                                "trigger_num_max": (input_thanks_follow_periodic_trigger_trigger_num_max, 'int'),
                            }
                        },
                        "lowest_price": (input_thanks_lowest_price, 'float')
                    }

            
              
              
                if config.get("webui", "show_card", "common_config", "database"):
                    config_mapping["database"] = {
                        "path": (input_database_path, 'str'),
                        "comment_enable": (switch_database_comment_enable, 'bool'),
                        "entrance_enable": (switch_database_entrance_enable, 'bool'),
                        "gift_enable": (switch_database_gift_enable, 'bool'),
                    }
                if config.get("webui", "show_card", "common_config", "abnormal_alarm"):
                    config_mapping["abnormal_alarm"] = {
                        "platform": {
                            "enable": (switch_abnormal_alarm_platform_enable, 'bool'),
                            "type": (select_abnormal_alarm_platform_type, 'str'),
                            "start_alarm_error_num": (input_abnormal_alarm_platform_start_alarm_error_num, 'int'),
                            "auto_restart_error_num": (input_abnormal_alarm_platform_auto_restart_error_num, 'int'),
                            "local_audio_path": (input_abnormal_alarm_platform_local_audio_path, 'str'),
                        },
                        "tts": {
                            "enable": (switch_abnormal_alarm_tts_enable, 'bool'),
                            "type": (select_abnormal_alarm_tts_type, 'str'),
                            "start_alarm_error_num": (input_abnormal_alarm_tts_start_alarm_error_num, 'int'),
                            "auto_restart_error_num": (input_abnormal_alarm_tts_auto_restart_error_num, 'int'),
                            "local_audio_path": (input_abnormal_alarm_tts_local_audio_path, 'str'),
                        },
                        "svc": {
                            "enable": (switch_abnormal_alarm_svc_enable, 'bool'),
                            "type": (select_abnormal_alarm_svc_type, 'str'),
                            "start_alarm_error_num": (input_abnormal_alarm_svc_start_alarm_error_num, 'int'),
                            "auto_restart_error_num": (input_abnormal_alarm_svc_auto_restart_error_num, 'int'),
                            "local_audio_path": (input_abnormal_alarm_svc_local_audio_path, 'str'),
                        },
                      
                        
                        "other": {
                            "enable": (switch_abnormal_alarm_other_enable, 'bool'),
                            "type": (select_abnormal_alarm_other_type, 'str'),
                            "start_alarm_error_num": (input_abnormal_alarm_other_start_alarm_error_num, 'int'),
                            "auto_restart_error_num": (input_abnormal_alarm_other_auto_restart_error_num, 'int'),
                            "local_audio_path": (input_abnormal_alarm_other_local_audio_path, 'str'),
                        },
                    }

                config_data = update_config(config_mapping, config, config_data, "common_config")
                
                
                # 动态配置
                if config.get("webui", "show_card", "common_config", "trends_config"):
                    config_data["trends_config"]["enable"] = switch_trends_config_enable.value
                    tmp_arr = []
                    # logger.info(trends_config_path_var)
                    for index in range(len(trends_config_path_var) // 2):
                        tmp_json = {
                            "online_num": "0-999999999",
                            "path": "config.json"
                        }
                        tmp_json["online_num"] = trends_config_path_var[str(2 * index)].value
                        tmp_json["path"] = trends_config_path_var[str(2 * index + 1)].value

                        tmp_arr.append(tmp_json)
                    # logger.info(tmp_arr)
                    config_data["trends_config"]["path"] = tmp_arr


                   
            """
            TTS
            """
            if True:
                config_mapping = {}

                if config.get("webui", "show_card", "tts", "edge-tts"):
                    config_mapping["edge-tts"] = {
                        "voice": (select_edge_tts_voice, 'str'),
                        "rate": (input_edge_tts_rate, 'str'),
                        "volume": (input_edge_tts_volume, 'str'),
                        "proxy": (input_edge_tts_proxy, 'str'),
                    }
                if config.get("webui", "show_card", "tts", "gsvi"): 
                    config_mapping["gsvi"] = {
                        "api_ip_port": (input_gsvi_ip_port, 'str'),
                        "model_name": (select_gsvi_models, 'str'),
                        "prompt_text_lang": (select_gsvi_lang, 'str'),
                        "emotion": (select_gsvi_emotion, 'str')
                    }
                if config.get("webui", "show_card", "tts", "gpt_sovits"):
                    config_mapping["gpt_sovits"] = {
                        "type": (select_gpt_sovits_type, 'str'),
                        "gradio_ip_port": (input_gpt_sovits_gradio_ip_port, 'str'),
                        "api_ip_port": (input_gpt_sovits_api_ip_port, 'str'),
                        "ref_audio_path": (input_gpt_sovits_ref_audio_path, 'str'),
                        "prompt_text": (input_gpt_sovits_prompt_text, 'str'),
                        "prompt_language": (select_gpt_sovits_prompt_language, 'str'),
                        "language": (select_gpt_sovits_language, 'str'),
                        "cut": (select_gpt_sovits_cut, 'str'),
                        "gpt_model_path": (input_gpt_sovits_gpt_model_path, 'str'),
                        "sovits_model_path": (input_gpt_sovits_sovits_model_path, 'str'),
                        "v2_api_0821": {
                            "ref_audio_path": (input_gpt_sovits_v2_api_0821_ref_audio_path, 'str'),
                            "prompt_text": (input_gpt_sovits_v2_api_0821_prompt_text, 'str'),
                            "prompt_lang": (select_gpt_sovits_v2_api_0821_prompt_lang, 'str'),
                            "text_lang": (select_gpt_sovits_v2_api_0821_text_lang, 'str'),
                            "text_split_method": (select_gpt_sovits_v2_api_0821_text_split_method, 'str'),
                            "top_k": (input_gpt_sovits_v2_api_0821_top_k, 'int'),
                            "top_p": (input_gpt_sovits_v2_api_0821_top_p, 'float'),
                            "temperature": (input_gpt_sovits_v2_api_0821_temperature, 'float'),
                            "batch_size": (input_gpt_sovits_v2_api_0821_batch_size, 'int'),
                            "batch_threshold": (input_gpt_sovits_v2_api_0821_batch_threshold, 'float'),
                            "split_bucket": (switch_gpt_sovits_v2_api_0821_split_bucket, 'bool'),
                            "speed_factor": (input_gpt_sovits_v2_api_0821_speed_factor, 'float'),
                            "fragment_interval": (input_gpt_sovits_v2_api_0821_fragment_interval, 'float'),
                            "seed": (input_gpt_sovits_v2_api_0821_seed, 'int'),
                            "media_type": (input_gpt_sovits_v2_api_0821_media_type, 'str'),
                            "parallel_infer": (switch_gpt_sovits_v2_api_0821_parallel_infer, 'bool'),
                            "repetition_penalty": (input_gpt_sovits_v2_api_0821_repetition_penalty, 'float'),
                        },
            
                    }

                config_data = update_config(config_mapping, config, config_data, "tts")

 
            """
            数据分析
            """
            if True:
                config_mapping = {
                    "data_analysis": {
                        "comment_word_cloud": {
                            "top_num": (input_data_analysis_comment_word_cloud_top_num, 'int'),
                        },
                        "integral": {
                            "top_num": (input_data_analysis_integral_top_num, 'int'),
                        },
                        "gift": {
                            "top_num": (input_data_analysis_gift_top_num, 'int'),
                        },
                    }
                }
                config_data = update_config(config_mapping, config, config_data, None)

            """
            UI配置
            """
            if True:
                config_mapping = {
                    "webui": {
                        "title": (input_webui_title, 'str'),
                        "ip": (input_webui_ip, 'str'),
                        "port": (input_webui_port, 'int'),
                        "auto_run": (switch_webui_auto_run, 'bool'),
                        "local_dir_to_endpoint": {
                            "enable": (switch_webui_local_dir_to_endpoint_enable, 'bool'),
                        },
                       
                        
                        "theme": {
                            "choose": (select_webui_theme_choose, 'str'),
                        },
                    },
                }

                config_data = update_config(config_mapping, config, config_data, None)

                tmp_arr = []
                for index in range(len(webui_local_dir_to_endpoint_config_var) // 2):
                    tmp_json = {
                        "url_path": "",
                        "local_dir": ""
                    }
                    tmp_json["url_path"] = webui_local_dir_to_endpoint_config_var[str(2 * index)].value
                    tmp_json["local_dir"] = webui_local_dir_to_endpoint_config_var[str(2 * index + 1)].value

                    tmp_arr.append(tmp_json)
                # logger.info(tmp_arr)
                config_data["webui"]["local_dir_to_endpoint"]["config"] = tmp_arr

                
            return config_data
        except Exception as e:
            logger.error(f"无法读取webui配置到变量！\n{e}")
            ui.notify(position="top", type="negative", message=f"无法读取webui配置到变量！\n{e}")
            logger.error(traceback.format_exc())

            return None

    # 保存配置
    def save_config():
        """
        保存配置到本地配置文件中
        """
        global config, config_path

        # 配置检查
        if not check_config():
            return False

        try:
            with open(config_path, 'r', encoding="utf-8") as config_file:
                config_data = json.load(config_file)
        except Exception as e:
            logger.error(f"无法读取配置文件！\n{e}")
            ui.notify(position="top", type="negative", message=f"无法读取配置文件！{e}")
            return False

        # 读取webui配置到dict变量
        config_data = webui_config_to_dict(config_data)
        if config_data is None:
            return False


        # 写入配置到配置文件
        try:
            with open(config_path, 'w', encoding="utf-8") as config_file:
                json.dump(config_data, config_file, indent=2, ensure_ascii=False)
                config_file.flush()  # 刷新缓冲区，确保写入立即生效

            logger.info("配置数据已成功写入文件！")
            ui.notify(position="top", type="positive", message="配置数据已成功写入文件！")

            return True
        except Exception as e:
            logger.error(f"无法写入配置文件！\n{str(e)}")
            ui.notify(position="top", type="negative", message=f"无法写入配置文件！\n{str(e)}")
            return False
        


    """

    ..............................................................................................................
    ..............................................................................................................
    ..........................,]].................................................................................
    .........................O@@@@^...............................................................................
    .....=@@@@@`.....O@@@....,\@@[.....................................,@@@@@@@@@@]....O@@@^......=@@@@....O@@@^..
    .....=@@@@@@.....O@@@............................................=@@@@/`..,[@@/....O@@@^......=@@@@....O@@@^..
    .....=@@@@@@@....O@@@....,]]]].......]@@@@@]`.....,/@@@@\`....../@@@@..............O@@@^......=@@@@....O@@@^..
    .....=@@@/@@@\...O@@@....=@@@@....,@@@@@@@@@@^..,@@@@@@@@@@\...=@@@@...............O@@@^......=@@@@....O@@@^..
    .....=@@@^,@@@\..O@@@....=@@@@...,@@@@`........=@@@/....=@@@\..=@@@@....]]]]]]]]...O@@@^......=@@@@....O@@@^..
    .....=@@@^.=@@@^.O@@@....=@@@@...O@@@^.........@@@@......@@@@..=@@@@....=@@@@@@@...O@@@^......=@@@@....O@@@^..
    .....=@@@^..\@@@^=@@@....=@@@@...@@@@^........,@@@@@@@@@@@@@@..=@@@@.......=@@@@...O@@@^......=@@@@....O@@@^..
    .....=@@@^...\@@@/@@@....=@@@@...O@@@^.........@@@@`...........,@@@@`......=@@@@...O@@@^......=@@@@....O@@@^..
    .....=@@@^....@@@@@@@....=@@@@...,@@@@`........=@@@@......,.....=@@@@`.....=@@@@...=@@@@`.....@@@@^....O@@@^..
    .....=@@@^....,@@@@@@....=@@@@....,@@@@@@@@@@`..=@@@@@@@@@@@`....,@@@@@@@@@@@@@@....,@@@@@@@@@@@@`.....O@@@^..
    .....,[[[`.....,[[[[[....,[[[[.......[@@@@@[`.....,[@@@@@[`.........,\@@@@@@[`.........[@@@@@@[........[[[[`..
    ..............................................................................................................
    ..............................................................................................................

    """

    # 语音合成所有配置项
    audio_synthesis_type_options = {
        'none': '不启用', 
        'edge-tts': 'Edge-TTS', 
        'gpt_sovits': 'GPT_SoVITS',
        'gsvi': 'GSVI',

    }

    # 聊天类型所有配置项
    

    platform_options = {
        'talk': '聊天模式', 
        'bilibili2': '哔哩哔哩2', 
    }

    with ui.tabs().classes('w-full') as tabs:
        common_config_page = ui.tab('通用配置')
        tts_page = ui.tab('文本转语音')
        data_analysis_page = ui.tab('数据分析')
        web_page = ui.tab('页面配置')

    with ui.tab_panels(tabs, value=common_config_page).classes('w-full'):
        with ui.tab_panel(common_config_page).style(tab_panel_css):
            with ui.row():
                
                select_platform = ui.select(
                    label='平台', 
                    options=platform_options, 
                    value=config.get("platform")
                ).style("width:200px;")

                input_room_display_id = ui.input(label='直播间号', placeholder='一般为直播间URL最后/后面的字母或数字', value=config.get("room_display_id")).style("width:200px;").tooltip('一般为直播间URL最后/后面的字母或数字')

                select_audio_synthesis_type = ui.select(
                    label='语音合成', 
                    options=audio_synthesis_type_options, 
                    value=config.get("audio_synthesis_type")
                ).style("width:200px;").tooltip('选用的TTS类型，所有的文本内容最终都将通过此TTS进行语音合成')

            with ui.row():
                select_need_lang = ui.select(
                    label='回复语言', 
                    options={'none': '所有', 'zh': '中文', 'en': '英文', 'jp': '日文'}, 
                    value=config.get("need_lang")
                ).style("width:200px;").tooltip('限制回复的语言，如：选中中文，则只会回复中文提问，其他语言将被跳过')

                input_before_prompt = ui.input(label='提示词前缀', placeholder='此配置会追加在弹幕前，再发送给LLM处理', value=config.get("before_prompt")).style("width:200px;").tooltip('此配置会追加在弹幕前，再发送给LLM处理')
                input_after_prompt = ui.input(label='提示词后缀', placeholder='此配置会追加在弹幕后，再发送给LLM处理', value=config.get("after_prompt")).style("width:200px;").tooltip('此配置会追加在弹幕后，再发送给LLM处理')
                switch_comment_template_enable = ui.switch('启用弹幕模板', value=config.get("comment_template", "enable")).style(switch_internal_css).tooltip('此配置会追加在弹幕后，再发送给LLM处理')
                input_comment_template_copywriting = ui.input(label='弹幕模板', value=config.get("comment_template", "copywriting"), placeholder='此配置会对弹幕内容进行修改，{}内为变量，会被替换为指定内容，请勿随意删除变量').style("width:200px;").tooltip('此配置会对弹幕内容进行修改，{}内为变量，会被替换为指定内容，请勿随意删除变量')
                switch_reply_template_enable = ui.switch('启用回复模板', value=config.get("reply_template", "enable")).style(switch_internal_css).tooltip('此配置会在LLM输出的答案中进行回复内容的重新构建')
                input_reply_template_username_max_len = ui.input(label='回复用户名的最大长度', value=config.get("reply_template", "username_max_len"), placeholder='回复用户名的最大长度').style("width:200px;").tooltip('回复用户名的最大长度')
                textarea_reply_template_copywriting = ui.textarea(
                    label='回复模板', 
                    placeholder='此配置会对LLM回复内容进行修改，{}内为变量，会被替换为指定内容，请勿随意删除变量', 
                    value=textarea_data_change(config.get("reply_template", "copywriting"))
                ).style("width:500px;").tooltip('此配置会对LLM回复内容进行修改，{}内为变量，会被替换为指定内容，请勿随意删除变量')

            with ui.expansion('功能管理', icon="settings", value=True).classes('w-full'):

                with ui.card().style(card_css):
                    ui.label('平台相关')
                    with ui.card().style(card_css):
                        ui.label('哔哩哔哩')
                        with ui.row():
                            select_bilibili_login_type = ui.select(
                                label='登录方式',
                                options={'cookie': 'cookie', '手机扫码': '手机扫码', '手机扫码-终端': '手机扫码-终端', '账号密码登录': '账号密码登录', 'open_live': '开放平台', '不登录': '不登录'},
                                value=config.get("bilibili", "login_type")
                            ).style("width:100px")
                            input_bilibili_cookie = ui.input(label='cookie', placeholder='b站登录后F12抓网络包获取cookie，强烈建议使用小号！有封号风险，虽然实际上没听说有人被封过', value=config.get("bilibili", "cookie")).style("width:500px;").tooltip('b站登录后F12抓网络包获取cookie，强烈建议使用小号！有封号风险，虽然实际上没听说有人被封过')
                            input_bilibili_ac_time_value = ui.input(label='ac_time_value', placeholder='b站登录后，F12控制台，输入window.localStorage.ac_time_value获取(如果没有，请重新登录)', value=config.get("bilibili", "ac_time_value")).style("width:500px;").tooltip('仅在平台：哔哩哔哩，情况下可选填写。b站登录后，F12控制台，输入window.localStorage.ac_time_value获取(如果没有，请重新登录)')
                        with ui.row():
                            input_bilibili_username = ui.input(label='账号', value=config.get("bilibili", "username"), placeholder='b站账号（建议使用小号）').style("width:300px;").tooltip('仅在平台：哔哩哔哩，登录方式：账号密码登录，情况下填写。b站账号（建议使用小号）')
                            input_bilibili_password = ui.input(label='密码', value=config.get("bilibili", "password"), placeholder='b站密码（建议使用小号）').style("width:300px;").tooltip('仅在平台：哔哩哔哩，登录方式：账号密码登录，情况下填写。b站密码（建议使用小号）')
                        with ui.row():
                            with ui.card().style(card_css):
                                ui.label('开放平台')
                                with ui.row():
                                    input_bilibili_open_live_ACCESS_KEY_ID = ui.input(label='ACCESS_KEY_ID', value=config.get("bilibili", "open_live", "ACCESS_KEY_ID"), placeholder='开放平台ACCESS_KEY_ID').style("width:160px;").tooltip('仅在平台：哔哩哔哩2，登录方式：开放平台，情况下填写。开放平台ACCESS_KEY_ID')
                                    input_bilibili_open_live_ACCESS_KEY_SECRET = ui.input(label='ACCESS_KEY_SECRET', value=config.get("bilibili", "open_live", "ACCESS_KEY_SECRET"), placeholder='开放平台ACCESS_KEY_SECRET').style("width:200px;").tooltip('仅在平台：哔哩哔哩2，登录方式：开放平台，情况下填写。开放平台ACCESS_KEY_SECRET')
                                    input_bilibili_open_live_APP_ID = ui.input(label='项目ID', value=config.get("bilibili", "open_live", "APP_ID"), placeholder='开放平台 创作者服务中心 项目ID').style("width:100px;").tooltip('仅在平台：哔哩哔哩2，登录方式：开放平台，情况下填写。开放平台 创作者服务中心 项目ID')
                                    input_bilibili_open_live_ROOM_OWNER_AUTH_CODE = ui.input(label='身份码', value=config.get("bilibili", "open_live", "ROOM_OWNER_AUTH_CODE"), placeholder='直播中心用户 身份码').style("width:100px;").tooltip('仅在平台：哔哩哔哩2，登录方式：开放平台，情况下填写。直播中心用户 身份码')
                            
                if config.get("webui", "show_card", "common_config", "play_audio"):
                    with ui.card().style(card_css):
                        ui.label('音频播放')
                        with ui.row():
                            switch_play_audio_enable = ui.switch('启用', value=config.get("play_audio", "enable")).style(switch_internal_css)
                            switch_play_audio_text_split_enable = ui.switch('启用文本切分', value=config.get("play_audio", "text_split_enable")).style(switch_internal_css).tooltip('启用后会将LLM等待合成音频的消息根据内部切分算法切分成多个短句，以便TTS快速合成')
                            switch_play_audio_info_to_callback = ui.switch('音频信息回传给内部接口', value=config.get("play_audio", "info_to_callback")).style(switch_internal_css).tooltip('启用后，会在当前音频播放完毕后，将程序中等待播放的音频信息传递给内部接口，用于闲时任务的闲时清零功能。\n不过这个功能会一定程度的拖慢程序运行，如果你不需要闲时清零，可以关闭此功能来提高响应速度')
                            
                        with ui.row():
                            input_play_audio_interval_num_min = ui.input(label='间隔时间重复次数最小值', value=config.get("play_audio", "interval_num_min"), placeholder='普通音频播放间隔时间，重复睡眠次数最小值。会在最大最小值之间随机生成一个重复次数，就是 次数 x 时间 = 最终间隔时间').tooltip('普通音频播放间隔时间重复睡眠次数最小值。会在最大最小值之间随机生成一个重复次数，就是 次数 x 时间 = 最终间隔时间')
                            input_play_audio_interval_num_max = ui.input(label='间隔时间重复次数最大值', value=config.get("play_audio", "interval_num_max"), placeholder='普通音频播放间隔时间，重复睡眠次数最大值。会在最大最小值之间随机生成一个重复次数，就是 次数 x 时间 = 最终间隔时间').tooltip('普通音频播放间隔时间重复睡眠次数最大值。会在最大最小值之间随机生成一个重复次数，就是 次数 x 时间 = 最终间隔时间')
                            input_play_audio_normal_interval_min = ui.input(label='普通音频播放间隔最小值', value=config.get("play_audio", "normal_interval_min"), placeholder='就是弹幕回复、唱歌等音频播放结束后到播放下一个音频之间的一个间隔时间，单位：秒').tooltip('就是弹幕回复、唱歌等音频播放结束后到播放下一个音频之间的一个间隔时间，单位：秒。次数 x 时间 = 最终间隔时间')
                            input_play_audio_normal_interval_max = ui.input(label='普通音频播放间隔最大值', value=config.get("play_audio", "normal_interval_max"), placeholder='就是弹幕回复、唱歌等音频播放结束后到播放下一个音频之间的一个间隔时间，单位：秒').tooltip('就是弹幕回复、唱歌等音频播放结束后到播放下一个音频之间的一个间隔时间，单位：秒。次数 x 时间 = 最终间隔时间')
                            
                            input_play_audio_out_path = ui.input(label='音频输出路径', placeholder='音频文件合成后存储的路径，支持相对路径或绝对路径', value=config.get("play_audio", "out_path")).tooltip('音频文件合成后存储的路径，支持相对路径或绝对路径')
                            select_play_audio_player = ui.select(
                                label='音频播放器',
                                options={'pygame': 'pygame', 'audio_player_v2': 'audio_player_v2', 'audio_player': 'audio_player'},
                                value=config.get("play_audio", "player")
                            ).style("width:200px").tooltip('选用的音频播放器，默认pygame不需要再安装其他程序。audio player需要单独安装对接，详情看视频教程')
                    
                        with ui.card().style(card_css):
                            ui.label('audio_player')
                            with ui.row():
                                input_audio_player_api_ip_port = ui.input(
                                    label='API地址', 
                                    value=config.get("audio_player", "api_ip_port"), 
                                    placeholder='audio_player的API地址，只需要 http://ip:端口 即可',
                                    validation={
                                        '请输入正确格式的URL': lambda value: common.is_url_check(value),
                                    }
                                ).style("width:200px;").tooltip('仅在 音频播放器：audio_player等，情况下填写。audio_player的API地址，只需要 http://ip:端口 即可')

                        
                if config.get("webui", "show_card", "common_config", "filter"):
                    with ui.card().style(card_css):
                        ui.label('过滤')    
                        
                        with ui.expansion('消息遗忘&保留设置', icon="settings", value=True).classes('w-full'):
                            with ui.element('div').classes('p-2 bg-blue-100'):
                                ui.label("遗忘间隔 指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，但会保留最新的n个数据；保留数 指的是保留最新收到的数据的数量")
                            with ui.grid(columns=4):
                                input_filter_comment_forget_duration = ui.input(
                                    label='弹幕遗忘间隔', 
                                    placeholder='例：1', 
                                    value=config.get("filter", "comment_forget_duration")
                                ).style("width:200px;").tooltip('指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，\n保留数据在以下配置中可以自定义')
                                input_filter_comment_forget_reserve_num = ui.input(label='弹幕保留数', placeholder='保留最新收到的数据的数量', value=config.get("filter", "comment_forget_reserve_num")).style("width:200px;").tooltip('保留最新收到的数据的数量')
                                input_filter_gift_forget_duration = ui.input(label='礼物遗忘间隔', placeholder='指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，\n保留数据在以下配置中可以自定义', value=config.get("filter", "gift_forget_duration")).style("width:200px;").tooltip('指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，\n保留数据在以下配置中可以自定义')
                                input_filter_gift_forget_reserve_num = ui.input(label='礼物保留数', placeholder='保留最新收到的数据的数量', value=config.get("filter", "gift_forget_reserve_num")).style("width:200px;").tooltip('保留最新收到的数据的数量')
                            with ui.grid(columns=4):
                                input_filter_schedule_forget_duration = ui.input(label='定时遗忘间隔', placeholder='指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，\n保留数据在以下配置中可以自定义', value=config.get("filter", "schedule_forget_duration")).style("width:200px;").tooltip('指的是每隔这个间隔时间（秒），就会丢弃这个间隔时间中接收到的数据，\n保留数据在以下配置中可以自定义')
                                input_filter_schedule_forget_reserve_num = ui.input(label='定时保留数', placeholder='保留最新收到的数据的数量', value=config.get("filter", "schedule_forget_reserve_num")).style("width:200px;").tooltip('保留最新收到的数据的数量')
                        with ui.expansion('限定时间段内数据重复丢弃', icon="settings", value=True).classes('w-full'):
                            with ui.row():
                                switch_filter_limited_time_deduplication_enable = ui.switch('启用', value=config.get("filter", "limited_time_deduplication", "enable")).style(switch_internal_css)
                                input_filter_limited_time_deduplication_comment = ui.input(label='弹幕检测周期', value=config.get("filter", "limited_time_deduplication", "comment"), placeholder='在这个周期时间（秒）内，重复的数据将被丢弃').style("width:200px;").tooltip('在这个周期时间（秒）内，重复的数据将被丢弃')
                                input_filter_limited_time_deduplication_gift = ui.input(label='礼物检测周期', value=config.get("filter", "limited_time_deduplication", "gift"), placeholder='在这个周期时间（秒）内，重复的数据将被丢弃').style("width:200px;").tooltip('在这个周期时间（秒）内，重复的数据将被丢弃')
                                input_filter_limited_time_deduplication_entrance = ui.input(label='入场检测周期', value=config.get("filter", "limited_time_deduplication", "entrance"), placeholder='在这个周期时间（秒）内，重复的数据将被丢弃').style("width:200px;").tooltip('在这个周期时间（秒）内，重复的数据将被丢弃')
                                    
                        with ui.expansion('待合成音频的消息&待播放音频队列', icon="settings", value=True).classes('w-full'):
                            with ui.row():
                                input_filter_message_queue_max_len = ui.input(label='消息队列最大保留长度', placeholder='收到的消息，生成的文本内容，会根据优先级存入消息队列，当新消息的优先级低于队列中所有的消息且超过此长度时，此消息将被丢弃', value=config.get("filter", "message_queue_max_len")).style("width:160px;").tooltip('收到的消息，生成的文本内容，会根据优先级存入消息队列，当新消息的优先级低于队列中所有的消息且超过此长度时，此消息将被丢弃')
                                input_filter_voice_tmp_path_queue_max_len = ui.input(label='音频播放队列最大保留长度', placeholder='合成后的音频，会根据优先级存入待播放音频队列，当新音频的优先级低于队列中所有的音频且超过此长度时，此音频将被丢弃', value=config.get("filter", "voice_tmp_path_queue_max_len")).style("width:200px;").tooltip('合成后的音频，会根据优先级存入待播放音频队列，当新音频的优先级低于队列中所有的音频且超过此长度时，此音频将被丢弃')

                                input_filter_voice_tmp_path_queue_min_start_play = ui.input(
                                    label='音频播放队列首次触发播放阈值', 
                                    placeholder='正整数 例如：20，如果你不想开播前缓冲一定数量的音频，请配置0', 
                                    value=config.get("filter", "voice_tmp_path_queue_min_start_play")
                                ).style("width:200px;").tooltip('此功能用于缓存一定数量的音频后再开始播放。如果你不想开播前缓冲一定数量的音频，请配置0；如果你想提前准备一些音频，如因为TTS合成慢的原因，可以配置此值，让TTS提前合成你的其他任务触发的内容')

                                with ui.element('div').classes('p-2 bg-blue-100'):
                                    ui.label("下方优先级配置，请使用正整数。数字越大，优先级越高，就会优先合成音频播放")
                                    ui.label("另外需要注意，由于shi山原因，目前这个队列内容是文本切分后计算的长度，所以如果回复内容过长，可能会有丢数据的情况")
                            with ui.grid(columns=5):
                                input_filter_priority_mapping_comment = ui.input(label='弹幕回复 优先级', value=config.get("filter", "priority_mapping", "comment"), placeholder='数字越大，优先级越高').style("width:200px;").tooltip('数字越大，优先级越高')
                                input_filter_priority_mapping_copywriting = ui.input(label='文案 优先级', value=config.get("filter", "priority_mapping", "copywriting"), placeholder='数字越大，优先级越高，文案页的文案，但这个并非文本，所以暂时没啥用，预留').style("width:200px;").tooltip('数字越大，优先级越高')
                                
                            with ui.grid(columns=5):
                                input_filter_priority_mapping_read_comment = ui.input(label='念弹幕 优先级', value=config.get("filter", "priority_mapping", "read_comment"), placeholder='数字越大，优先级越高').style("width:200px;").tooltip('数字越大，优先级越高')
                                input_filter_priority_mapping_entrance = ui.input(label='入场欢迎 优先级', value=config.get("filter", "priority_mapping", "entrance"), placeholder='数字越大，优先级越高').style("width:200px;").tooltip('数字越大，优先级越高')
                                input_filter_priority_mapping_gift = ui.input(label='礼物答谢 优先级', value=config.get("filter", "priority_mapping", "gift"), placeholder='数字越大，优先级越高').style("width:200px;").tooltip('数字越大，优先级越高')
                                input_filter_priority_mapping_follow = ui.input(label='关注答谢 优先级', value=config.get("filter", "priority_mapping", "follow"), placeholder='数字越大，优先级越高').style("width:200px;").tooltip('数字越大，优先级越高')
                
                    
                            
            with ui.expansion('互动功能', icon="question_answer", value=True).classes('w-full'):

                if config.get("webui", "show_card", "common_config", "read_comment"):
                    with ui.card().style(card_css):
                        ui.label('念弹幕')
                        with ui.grid(columns=4):
                            switch_read_comment_enable = ui.switch('启用', value=config.get("read_comment", "enable")).style(switch_internal_css)
                            switch_read_comment_read_username_enable = ui.switch('念用户名', value=config.get("read_comment", "read_username_enable")).style(switch_internal_css)
                            input_read_comment_username_max_len = ui.input(label='用户名最大长度', value=config.get("read_comment", "username_max_len"), placeholder='需要保留的用户名的最大长度，超出部分将被丢弃').style("width:100px;").tooltip('需要保留的用户名的最大长度，超出部分将被丢弃')
                            switch_read_comment_voice_change = ui.switch('变声', value=config.get("read_comment", "voice_change")).style(switch_internal_css)
                        with ui.grid(columns=2):
                            textarea_read_comment_read_username_copywriting = ui.textarea(
                                label='念用户名文案', 
                                placeholder='念用户名时使用的文案，可以自定义编辑多个（换行分隔），实际中会随机一个使用', 
                                value=textarea_data_change(config.get("read_comment", "read_username_copywriting"))
                            ).style("width:500px;").tooltip('念用户名时使用的文案，可以自定义编辑多个（换行分隔），实际中会随机一个使用')
                        with ui.row():
                            switch_read_comment_periodic_trigger_enable = ui.switch('周期性触发启用', value=config.get("read_comment", "periodic_trigger", "enable")).style(switch_internal_css)
                            input_read_comment_periodic_trigger_periodic_time_min = ui.input(
                                label='触发周期最小值', 
                                value=config.get("read_comment", "periodic_trigger", "periodic_time_min"), 
                                placeholder='例如：5'
                            ).style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                            input_read_comment_periodic_trigger_periodic_time_max = ui.input(
                                label='触发周期最大值', 
                                value=config.get("read_comment", "periodic_trigger", "periodic_time_max"), 
                                placeholder='例如：10'
                            ).style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                            input_read_comment_periodic_trigger_trigger_num_min = ui.input(
                                label='触发次数最小值', 
                                value=config.get("read_comment", "periodic_trigger", "trigger_num_min"), 
                                placeholder='例如：0'
                            ).style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成')
                            input_read_comment_periodic_trigger_trigger_num_max = ui.input(
                                label='触发次数最大值', 
                                value=config.get("read_comment", "periodic_trigger", "trigger_num_max"), 
                                placeholder='例如：1'
                            ).style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成')
                
                if config.get("webui", "show_card", "common_config", "thanks"):
                    with ui.card().style(card_css):
                        ui.label('答谢')  
                        with ui.row():
                            input_thanks_username_max_len = ui.input(label='用户名最大长度', value=config.get("thanks", "username_max_len"), placeholder='需要保留的用户名的最大长度，超出部分将被丢弃').style("width:100px;")       
                        with ui.expansion('入场设置', icon="settings", value=True).classes('w-full'):
                            with ui.row():
                                switch_thanks_entrance_enable = ui.switch('启用入场欢迎', value=config.get("thanks", "entrance_enable")).style(switch_internal_css)
                                switch_thanks_entrance_random = ui.switch('随机选取', value=config.get("thanks", "entrance_random")).style(switch_internal_css)
                                textarea_thanks_entrance_copy = ui.textarea(label='入场文案', value=textarea_data_change(config.get("thanks", "entrance_copy")), placeholder='用户进入直播间的相关文案，请勿动 {username}，此字符串用于替换用户名').style("width:500px;")

                            with ui.row():
                                switch_thanks_entrance_periodic_trigger_enable = ui.switch('周期性触发启用', value=config.get("thanks", "entrance", "periodic_trigger", "enable")).style(switch_internal_css)
                                input_thanks_entrance_periodic_trigger_periodic_time_min = ui.input(label='触发周期最小值', value=config.get("thanks", "entrance", "periodic_trigger", "periodic_time_min"), placeholder='每隔这个周期的时间会触发n次此功能').style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_entrance_periodic_trigger_periodic_time_max = ui.input(label='触发周期最大值', value=config.get("thanks", "entrance", "periodic_trigger", "periodic_time_max"), placeholder='每隔这个周期的时间会触发n次此功能').style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_entrance_periodic_trigger_trigger_num_min = ui.input(label='触发次数最小值', value=config.get("thanks", "entrance", "periodic_trigger", "trigger_num_min"), placeholder='周期到后，会触发n次此功能').style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                                input_thanks_entrance_periodic_trigger_trigger_num_max = ui.input(label='触发次数最大值', value=config.get("thanks", "entrance", "periodic_trigger", "trigger_num_max"), placeholder='周期到后，会触发n次此功能').style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                        with ui.expansion('礼物设置', icon="settings", value=True).classes('w-full'):
                            with ui.row():
                                switch_thanks_gift_enable = ui.switch('启用礼物答谢', value=config.get("thanks", "gift_enable")).style(switch_internal_css)
                                switch_thanks_gift_random = ui.switch('随机选取', value=config.get("thanks", "gift_random")).style(switch_internal_css)
                                textarea_thanks_gift_copy = ui.textarea(label='礼物文案', value=textarea_data_change(config.get("thanks", "gift_copy")), placeholder='用户赠送礼物的相关文案，请勿动 {username} 和 {gift_name}，此字符串用于替换用户名和礼物名').style("width:500px;")
                                input_thanks_lowest_price = ui.input(label='最低答谢礼物价格', value=config.get("thanks", "lowest_price"), placeholder='设置最低答谢礼物的价格（元），低于这个设置的礼物不会触发答谢').style("width:100px;")
                            with ui.row():
                                switch_thanks_gift_periodic_trigger_enable = ui.switch('周期性触发启用', value=config.get("thanks", "gift", "periodic_trigger", "enable")).style(switch_internal_css)
                                input_thanks_gift_periodic_trigger_periodic_time_min = ui.input(label='触发周期最小值', value=config.get("thanks", "gift", "periodic_trigger", "periodic_time_min"), placeholder='每隔这个周期的时间会触发n次此功能').style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_gift_periodic_trigger_periodic_time_max = ui.input(label='触发周期最大值', value=config.get("thanks", "gift", "periodic_trigger", "periodic_time_max"), placeholder='每隔这个周期的时间会触发n次此功能').style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_gift_periodic_trigger_trigger_num_min = ui.input(label='触发次数最小值', value=config.get("thanks", "gift", "periodic_trigger", "trigger_num_min"), placeholder='周期到后，会触发n次此功能').style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                                input_thanks_gift_periodic_trigger_trigger_num_max = ui.input(label='触发次数最大值', value=config.get("thanks", "gift", "periodic_trigger", "trigger_num_max"), placeholder='周期到后，会触发n次此功能').style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                        with ui.expansion('关注设置', icon="settings", value=True).classes('w-full'):
                            with ui.row():
                                switch_thanks_follow_enable = ui.switch('启用关注答谢', value=config.get("thanks", "follow_enable")).style(switch_internal_css)
                                switch_thanks_follow_random = ui.switch('随机选取', value=config.get("thanks", "follow_random")).style(switch_internal_css)
                                textarea_thanks_follow_copy = ui.textarea(label='关注文案', value=textarea_data_change(config.get("thanks", "follow_copy")), placeholder='用户关注时的相关文案，请勿动 {username}，此字符串用于替换用户名').style("width:500px;")
                            with ui.row():
                                switch_thanks_follow_periodic_trigger_enable = ui.switch(
                                    '周期性触发启用', 
                                    value=config.get("thanks", "follow", "periodic_trigger", "enable")
                                ).style(switch_internal_css)
                                input_thanks_follow_periodic_trigger_periodic_time_min = ui.input(
                                    label='触发周期最小值', 
                                    value=config.get("thanks", "follow", "periodic_trigger", "periodic_time_min"), 
                                    placeholder='每隔这个周期的时间会触发n次此功能'
                                ).style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_follow_periodic_trigger_periodic_time_max = ui.input(
                                    label='触发周期最大值', 
                                    value=config.get("thanks", "follow", "periodic_trigger", "periodic_time_max"), 
                                    placeholder='每隔这个周期的时间会触发n次此功能'
                                ).style("width:100px;").tooltip('每隔这个周期的时间会触发n次此功能，周期时间从最大最小值之间随机生成')
                                input_thanks_follow_periodic_trigger_trigger_num_min = ui.input(
                                    label='触发次数最小值', 
                                    value=config.get("thanks", "follow", "periodic_trigger", "trigger_num_min"), 
                                    placeholder='周期到后，会触发n次此功能'
                                ).style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                                input_thanks_follow_periodic_trigger_trigger_num_max = ui.input(
                                    label='触发次数最大值', 
                                    value=config.get("thanks", "follow", "periodic_trigger", "trigger_num_max"), 
                                    placeholder='周期到后，会触发n次此功能'
                                ).style("width:100px;").tooltip('周期到后，会触发n次此功能，次数从最大最小值之间随机生成') 
                        
                

            with ui.expansion('高级功能', icon="view_in_ar", value=True).classes('w-full'):
                if config.get("webui", "show_card", "common_config", "log"):
                    with ui.card().style(card_css):
                        ui.label('日志')
                        with ui.grid(columns=4):
                            switch_captions_enable = ui.switch('启用', value=config.get("captions", "enable")).style(switch_internal_css)

                            select_comment_log_type = ui.select(
                                label='弹幕日志类型',
                                options={'问答': '问答', '问题': '问题', '回答': '回答', '不记录': '不记录'},
                                value=config.get("comment_log_type")
                            )

                            input_captions_file_path = ui.input(label='字幕日志路径', value=config.get("captions", "file_path"), placeholder='字幕日志存储路径').style("width:200px;")
                            input_captions_raw_file_path = ui.input(label='原文字幕日志路径', placeholder='原文字幕日志存储路径',
                                                                value=config.get("captions", "raw_file_path")).style("width:200px;")

                if config.get("webui", "show_card", "common_config", "database"):  
                    with ui.card().style(card_css):
                        ui.label('数据库')
                        with ui.grid(columns=4):
                            switch_database_comment_enable = ui.switch('弹幕日志', value=config.get("database", "comment_enable")).style(switch_internal_css)
                            switch_database_entrance_enable = ui.switch('入场日志', value=config.get("database", "entrance_enable")).style(switch_internal_css)
                            switch_database_gift_enable = ui.switch('礼物日志', value=config.get("database", "gift_enable")).style(switch_internal_css)
                            input_database_path = ui.input(label='数据库路径', value=config.get("database", "path"), placeholder='数据库文件存储路径').style("width:200px;")
                            
                              
                if config.get("webui", "show_card", "common_config", "custom_cmd"):  
                    with ui.card().style(card_css):
                        ui.label('自定义命令')
                        with ui.row():
                            switch_custom_cmd_enable = ui.switch('启用', value=config.get("custom_cmd", "enable")).style(switch_internal_css)
                            select_custom_cmd_type = ui.select(
                                label='类型',
                                options={'弹幕': '弹幕'},
                                value=config.get("custom_cmd", "type")
                            ).style("width:200px")
                        with ui.row():
                            input_custom_cmd_index = ui.input(label='配置索引', value="", placeholder='配置组的排序号，就是说第一个组是1，第二个组是2，以此类推。请填写纯正整数')
                            button_custom_cmd_add = ui.button('增加配置组', on_click=custom_cmd_add, color=button_internal_color).style(button_internal_css)
                            button_custom_cmd_del = ui.button('删除配置组', on_click=lambda: custom_cmd_del(input_custom_cmd_index.value), color=button_internal_color).style(button_internal_css)
                        
                        custom_cmd_config_var = {}
                        custom_cmd_config_card = ui.card()
                        for index, custom_cmd_config in enumerate(config.get("custom_cmd", "config")):
                            with custom_cmd_config_card.style(card_css):
                                with ui.row():
                                    custom_cmd_config_var[str(7 * index)] = ui.textarea(label=f"关键词#{index + 1}", value=textarea_data_change(custom_cmd_config["keywords"]), placeholder='此处输入触发的关键词，多个请以换行分隔').style("width:200px;")
                                    custom_cmd_config_var[str(7 * index + 1)] = ui.input(label=f"相似度#{index + 1}", value=custom_cmd_config["similarity"], placeholder='关键词与用户输入的相似度，默认1即100%').style("width:100px;")
                                    custom_cmd_config_var[str(7 * index + 2)] = ui.textarea(
                                        label=f"API URL#{index + 1}", 
                                        value=custom_cmd_config["api_url"], 
                                        placeholder='发送HTTP请求的API链接', 
                                        validation={
                                            '请输入正确格式的URL': lambda value: common.is_url_check(value),
                                        }
                                    ).style("width:300px;").tooltip('发送HTTP请求的API链接')
                                    custom_cmd_config_var[str(7 * index + 3)] = ui.select(label=f"API类型#{index + 1}", value=custom_cmd_config["api_type"], options={"GET": "GET"}).style("width:100px;")
                                    custom_cmd_config_var[str(7 * index + 4)] = ui.select(label=f"请求返回数据类型#{index + 1}", value=custom_cmd_config["resp_data_type"], options={"json": "json", "content": "content"}).style("width:150px;")
                                    custom_cmd_config_var[str(7 * index + 5)] = ui.textarea(label=f"数据解析（eval执行）#{index + 1}", value=custom_cmd_config["data_analysis"], placeholder='数据解析，请不要随意修改resp变量，会被用于最后返回数据内容的解析').style("width:200px;").tooltip('数据解析，请不要随意修改resp变量，会被用于最后返回数据内容的解析')
                                    custom_cmd_config_var[str(7 * index + 6)] = ui.textarea(label=f"返回内容模板#{index + 1}", value=custom_cmd_config["resp_template"], placeholder='请不要随意删除data变量，支持动态变量，最终会合并成完成内容进行音频合成').style("width:300px;").tooltip("请不要随意删除data变量，支持动态变量，最终会合并成完成内容进行音频合成")


                if config.get("webui", "show_card", "common_config", "trends_config"):  
                    with ui.card().style(card_css):
                        ui.label('动态配置')
                        with ui.row():
                            switch_trends_config_enable = ui.switch('启用', value=config.get("trends_config", "enable")).style(switch_internal_css)
                        trends_config_path_var = {}
                        for index, trends_config_path in enumerate(config.get("trends_config", "path")):
                            with ui.grid(columns=2):
                                trends_config_path_var[str(2 * index)] = ui.input(label="在线人数范围", value=trends_config_path["online_num"], placeholder='在线人数范围，用减号-分隔，例如：0-10').style("width:200px;").tooltip("在线人数范围，用减号-分隔，例如：0-10")
                                trends_config_path_var[str(2 * index + 1)] = ui.input(label="配置路径", value=trends_config_path["path"], placeholder='此处输入加载的配置文件的路径').style("width:200px;").tooltip("此处输入加载的配置文件的路径")
                
                if config.get("webui", "show_card", "common_config", "abnormal_alarm"): 
                    with ui.card().style(card_css):
                        ui.label('异常报警')
                        with ui.row():
                            switch_abnormal_alarm_platform_enable = ui.switch('启用平台报警', value=config.get("abnormal_alarm", "platform", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_platform_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "platform", "type")
                            )
                            input_abnormal_alarm_platform_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "platform", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_platform_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "platform", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_platform_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "platform", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                        with ui.row():
                            switch_abnormal_alarm_llm_enable = ui.switch('启用LLM报警', value=config.get("abnormal_alarm", "llm", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_llm_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "llm", "type")
                            )
                            input_abnormal_alarm_llm_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "llm", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_llm_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "llm", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_llm_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "llm", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                        with ui.row():
                            switch_abnormal_alarm_tts_enable = ui.switch('启用TTS报警', value=config.get("abnormal_alarm", "tts", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_tts_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "tts", "type")
                            )
                            input_abnormal_alarm_tts_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "tts", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_tts_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "tts", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_tts_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "tts", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                        with ui.row():
                            switch_abnormal_alarm_svc_enable = ui.switch('启用SVC报警', value=config.get("abnormal_alarm", "svc", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_svc_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "svc", "type")
                            )
                            input_abnormal_alarm_svc_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "svc", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_svc_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "svc", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_svc_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "svc", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                        with ui.row():
                            switch_abnormal_alarm_visual_body_enable = ui.switch('启用虚拟身体报警', value=config.get("abnormal_alarm", "visual_body", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_visual_body_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "visual_body", "type")
                            )
                            input_abnormal_alarm_visual_body_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "visual_body", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_visual_body_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "visual_body", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_visual_body_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "visual_body", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                        with ui.row():
                            switch_abnormal_alarm_other_enable = ui.switch('启用其他报警', value=config.get("abnormal_alarm", "other", "enable")).style(switch_internal_css)
                            select_abnormal_alarm_other_type = ui.select(
                                label='类型',
                                options={'local_audio': '本地音频'},
                                value=config.get("abnormal_alarm", "other", "type")
                            )
                            input_abnormal_alarm_other_start_alarm_error_num = ui.input(label='开始报警错误数', value=config.get("abnormal_alarm", "other", "start_alarm_error_num"), placeholder='开始异常报警的错误数，超过这个数后就会报警').style("width:100px;")
                            input_abnormal_alarm_other_auto_restart_error_num = ui.input(label='自动重启错误数', value=config.get("abnormal_alarm", "other", "auto_restart_error_num"), placeholder='记得先启用“自动运行”功能。自动重启的错误数，超过这个数后就会自动重启webui。').style("width:100px;")
                            input_abnormal_alarm_other_local_audio_path = ui.input(label='本地音频路径', value=config.get("abnormal_alarm", "other", "local_audio_path"), placeholder='本地音频存储的文件路径（可以是多个音频，随机一个）').style("width:300px;")
                    
                
        with ui.tab_panel(tts_page).style(tab_panel_css):
            # 通用-合成试听音频
            async def tts_common_audio_synthesis():
                ui.notify(position="top", type="warning", message="音频合成中，将会阻塞其他任务运行，请勿做其他操作，查看日志情况，耐心等待")
                logger.warning("音频合成中，将会阻塞其他任务运行，请勿做其他操作，查看日志情况，耐心等待")
                
                content = input_tts_common_text.value
                audio_synthesis_type = select_tts_common_audio_synthesis_type.value

                # 使用本地配置进行音频合成，返回音频路径
                file_path = await audio.audio_synthesis_use_local_config(content, audio_synthesis_type)

                if file_path:
                    logger.info(f"音频合成成功，存储于：{file_path}")
                    ui.notify(position="top", type="positive", message=f"音频合成成功，存储于：{file_path}")
                else:
                    logger.error(f"音频合成失败！请查看日志排查问题")
                    ui.notify(position="top", type="negative", message=f"音频合成失败！请查看日志排查问题")
                    return

                def clear_tts_common_audio_card(file_path):
                    tts_common_audio_card.clear()
                    if common.del_file(file_path):
                        ui.notify(position="top", type="positive", message=f"删除文件成功：{file_path}")
                    else:
                        ui.notify(position="top", type="negative", message=f"删除文件失败：{file_path}")
                
                # 清空card
                tts_common_audio_card.clear()
                tmp_label = ui.label(f"音频合成成功，存储于：{file_path}")
                tmp_label.move(tts_common_audio_card)
                audio_tmp = ui.audio(src=file_path)
                audio_tmp.move(tts_common_audio_card)
                button_audio_del = ui.button('删除音频', on_click=lambda: clear_tts_common_audio_card(file_path), color=button_internal_color).style(button_internal_css)
                button_audio_del.move(tts_common_audio_card)
                
                
            with ui.card().style(card_css):
                ui.label("合成测试（只是测试，若确认使用此TTS，请前往 通用配置 配置 语音合成）")
                with ui.row():
                    select_tts_common_audio_synthesis_type = ui.select(
                        label='语音合成', 
                        options=audio_synthesis_type_options, 
                        value=config.get("audio_synthesis_type")
                    ).style("width:200px;")
                    input_tts_common_text = ui.input(label='待合成音频内容', placeholder='此处填写待合成的音频文本内容', value="此处填写待合成的音频文本内容，用于试听效果，类型切换不需要保存即可生效。").style("width:350px;")
                    button_tts_common_audio_synthesis = ui.button('试听', on_click=lambda: tts_common_audio_synthesis(), color=button_internal_color).style(button_internal_css)
                tts_common_audio_card = ui.card()
                with tts_common_audio_card.style(card_css):
                    with ui.row():
                        ui.label("此处显示生成的音频，仅显示最新合成的音频，可以在此操作删除合成的音频")

            if config.get("webui", "show_card", "tts", "edge-tts"):
                with ui.card().style(card_css):
                    ui.label("Edge-TTS")
                    with ui.row():
                        with open('data/edge-tts-voice-list.txt', 'r') as file:
                            file_content = file.read()
                        # 按行分割内容，并去除每行末尾的换行符
                        lines = file_content.strip().split('\n')
                        data_json = {}
                        for line in lines:
                            data_json[line] = line
                        select_edge_tts_voice = ui.select(
                            label='说话人', 
                            options=data_json, 
                            value=config.get("edge-tts", "voice")
                        )

                        input_edge_tts_rate = ui.input(label='语速增益', placeholder='语速增益 默认是 +0%，可以增减，注意 + - %符合别搞没了，不然会影响语音合成', value=config.get("edge-tts", "rate")).style("width:150px;").tooltip("语速增益 默认是 +0%，可以增减，注意 + - %符合别搞没了，不然会影响语音合成")

                        input_edge_tts_volume = ui.input(label='音量增益', placeholder='音量增益 默认是 +0%，可以增减，注意 + - %符合别搞没了，不然会影响语音合成', value=config.get("edge-tts", "volume")).style("width:150px;").tooltip("音量增益 默认是 +0%，可以增减，注意 + - %符合别搞没了，不然会影响语音合成")
                        input_edge_tts_proxy = ui.input(label='HTTP代理地址', placeholder='例：http://127.0.0.1:10809', value=config.get("edge-tts", "proxy")).style("width:300px;").tooltip("根据您的实际代理配置，例：http://127.0.0.1:10809")


            if config.get("webui", "show_card", "tts", "gsvi"): 
                with ui.card().style(card_css):
                    ui.label("GSVI")
                    with ui.row():
                        input_gsvi_ip_port = ui.input(
                            label='API地址（http）', 
                            placeholder='此处填写GSVI的API地址（http）', 
                            value=config.get("gsvi", "api_ip_port")
                            ).style("width:200px;")
                        button_get_gsvi_models = ui.button('获取模型', on_click=lambda: gsvi_set_init(), color=button_internal_color).style(button_internal_css)
                    with ui.row():
                        select_gsvi_models = ui.select(label='选择模型', options=[]).style("width:300px;")
                        select_gsvi_lang = ui.select(label='模型语言', options=[]).style("width:150px;")
                        select_gsvi_emotion = ui.select(label='情感', options=[]).style("width:150px;")

            if config.get("webui", "show_card", "tts", "gpt_sovits"): 
                with ui.card().style(card_css):
                    ui.label("GPT-SoVITS")
                    with ui.row():
                        select_gpt_sovits_type = ui.select(
                            label='API类型', 
                            options={
                                'api':'api', 
                                'api_0322':'api_0322', 
                                'api_0706':'api_0706', 
                                'v2_api_0821': 'v2_api_0821', 
                                'webtts':'WebTTS', 
                                'gradio_0322':'gradio_0322',
                                
                            }, 
                            value=config.get("gpt_sovits", "type")
                        ).style("width:100px;")
                        input_gpt_sovits_gradio_ip_port = ui.input(
                            label='Gradio API地址', 
                            value=config.get("gpt_sovits", "gradio_ip_port"), 
                            placeholder='官方webui程序启动后gradio监听的地址',
                            validation={
                                '请输入正确格式的URL': lambda value: common.is_url_check(value),
                            }
                        ).style("width:200px;")
                        input_gpt_sovits_api_ip_port = ui.input(
                            label='API地址（http）', 
                            value=config.get("gpt_sovits", "api_ip_port"), 
                            placeholder='官方API程序启动后监听的地址',
                            validation={
                                '请输入正确格式的URL': lambda value: common.is_url_check(value),
                            }
                        ).style("width:200px;")
                        
                    
                    with ui.row():
                        input_gpt_sovits_gpt_model_path = ui.input(
                            label='GPT模型路径', 
                            value=config.get("gpt_sovits", "gpt_model_path"), 
                            placeholder='GPT模型路径，填绝对路径'
                        ).style("width:300px;")
                        input_gpt_sovits_sovits_model_path = ui.input(label='SOVITS模型路径', value=config.get("gpt_sovits", "sovits_model_path"), placeholder='SOVITS模型路径，填绝对路径').style("width:300px;")
                        button_gpt_sovits_set_model = ui.button('加载模型', on_click=lambda: gpt_sovits_set_model(), color=button_internal_color).style(button_internal_css)
                    
                    with ui.card().style(card_css):
                        ui.label("api")
                        with ui.row():
                            input_gpt_sovits_ref_audio_path = ui.input(label='参考音频路径', value=config.get("gpt_sovits", "ref_audio_path"), placeholder='参考音频路径，建议填绝对路径').style("width:300px;")
                            input_gpt_sovits_prompt_text = ui.input(label='参考音频的文本', value=config.get("gpt_sovits", "prompt_text"), placeholder='参考音频的文本').style("width:200px;")
                            select_gpt_sovits_prompt_language = ui.select(
                                label='参考音频的语种', 
                                options={'中文':'中文', '日文':'日文', '英文':'英文'}, 
                                value=config.get("gpt_sovits", "prompt_language")
                            ).style("width:150px;")
                            select_gpt_sovits_language = ui.select(
                                label='需要合成的语种', 
                                options={'自动识别':'自动识别', '中文':'中文', '日文':'日文', '英文':'英文'}, 
                                value=config.get("gpt_sovits", "language")
                            ).style("width:150px;")
                            select_gpt_sovits_cut = ui.select(
                                label='语句切分', 
                                options={
                                    '不切':'不切', 
                                    '凑四句一切':'凑四句一切', 
                                    '凑50字一切':'凑50字一切', 
                                    '按中文句号。切':'按中文句号。切', 
                                    '按英文句号.切':'按英文句号.切',
                                    '按标点符号切':'按标点符号切'
                                }, 
                                value=config.get("gpt_sovits", "cut")
                            ).style("width:200px;")
                    
                        
                    with ui.card().style(card_css):
                        ui.label("v2_api_0821")
                        with ui.row():
                            input_gpt_sovits_v2_api_0821_ref_audio_path = ui.input(label='参考音频路径', value=config.get("gpt_sovits", "v2_api_0821", "ref_audio_path"), placeholder='参考音频路径，建议填绝对路径').style("width:300px;")
                            input_gpt_sovits_v2_api_0821_prompt_text = ui.input(label='参考音频的文本', value=config.get("gpt_sovits", "v2_api_0821", "prompt_text"), placeholder='参考音频的文本').style("width:200px;")
                            select_gpt_sovits_v2_api_0821_prompt_lang = ui.select(
                                label='参考音频的语种', 
                                options={'zh':'中文', 'ja':'日文', 'en':'英文'}, 
                                value=config.get("gpt_sovits", "v2_api_0821", "prompt_lang")
                            ).style("width:150px;")
                            select_gpt_sovits_v2_api_0821_text_lang = ui.select(
                                label='需要合成的语种', 
                                options={
                                    "all_zh": "中文",
                                    "all_yue": "粤语",
                                    "en": "英文",
                                    "all_ja": "日文",
                                    "all_ko": "韩文",
                                    "zh": "中英混合",
                                    "yue": "粤英混合",
                                    "ja": "日英混合",
                                    "ko": "韩英混合",
                                    "auto": "多语种混合",    #多语种启动切分识别语种
                                    "auto_yue": "多语种混合(粤语)",
                                }, 
                                value=config.get("gpt_sovits", "v2_api_0821", "text_lang")
                            ).style("width:150px;")
                            select_gpt_sovits_v2_api_0821_text_split_method = ui.select(
                                label='语句切分', 
                                options={
                                    'cut0':'不切', 
                                    'cut1':'凑四句一切', 
                                    'cut2':'凑50字一切', 
                                    'cut3':'按中文句号。切', 
                                    'cut4':'按英文句号.切',
                                    'cut5':'按标点符号切'
                                }, 
                                value=config.get("gpt_sovits", "v2_api_0821", "text_split_method")
                            ).style("width:200px;")
                        with ui.row():
                            input_gpt_sovits_v2_api_0821_top_k = ui.input(label='top_k', value=config.get("gpt_sovits", "v2_api_0821", "top_k"), placeholder='top_k').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_top_p = ui.input(label='top_p', value=config.get("gpt_sovits", "v2_api_0821", "top_p"), placeholder='top_p').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_temperature = ui.input(label='temperature', value=config.get("gpt_sovits", "v2_api_0821", "temperature"), placeholder='temperature').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_batch_size = ui.input(label='batch_size', value=config.get("gpt_sovits", "v2_api_0821", "batch_size"), placeholder='batch_size').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_batch_threshold = ui.input(label='batch_threshold', value=config.get("gpt_sovits", "v2_api_0821", "batch_threshold"), placeholder='batch_threshold').style("width:100px;")
                            switch_gpt_sovits_v2_api_0821_split_bucket = ui.switch('split_bucket', value=config.get("gpt_sovits", "v2_api_0821", "split_bucket")).style(switch_internal_css)
                            input_gpt_sovits_v2_api_0821_speed_factor = ui.input(label='speed_factor', value=config.get("gpt_sovits", "v2_api_0821", "speed_factor"), placeholder='speed_factor').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_fragment_interval = ui.input(label='分段间隔(秒)', value=config.get("gpt_sovits", "v2_api_0821", "fragment_interval"), placeholder='fragment_interval').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_seed = ui.input(label='seed', value=config.get("gpt_sovits", "v2_api_0821", "seed"), placeholder='seed').style("width:100px;")
                            input_gpt_sovits_v2_api_0821_media_type = ui.input(label='media_type', value=config.get("gpt_sovits", "v2_api_0821", "media_type"), placeholder='media_type').style("width:100px;")
                            switch_gpt_sovits_v2_api_0821_parallel_infer = ui.switch('parallel_infer', value=config.get("gpt_sovits", "v2_api_0821", "parallel_infer")).style(switch_internal_css)
                            input_gpt_sovits_v2_api_0821_repetition_penalty = ui.input(label='repetition_penalty', value=config.get("gpt_sovits", "v2_api_0821", "repetition_penalty"), placeholder='repetition_penalty').style("width:100px;")
                            


            

        with ui.tab_panel(data_analysis_page).style(tab_panel_css):
            from utils.data_analysis import Data_Analysis

            data_analysis = Data_Analysis(config_path)

            data_analysis_comment_word_cloud_card = ui.card()
            with data_analysis_comment_word_cloud_card.style("width:100%;"):
                echart_comment_word_cloud = ui.echart(data_analysis.get_comment_word_cloud_option(
                    int(config.get("data_analysis", "comment_word_cloud", "top_num")))
                ).style(echart_css)
        
                with ui.row():
                    input_data_analysis_comment_word_cloud_top_num = ui.input(label='前N个关键词', value=config.get("data_analysis", "comment_word_cloud", "top_num"), placeholder='筛选前N个弹幕关键词做为词云数据')
                    def update_echart_comment_word_cloud():
                        data_analysis_comment_word_cloud_card.remove(0)
                        echart_comment_word_cloud = ui.echart(data_analysis.get_comment_word_cloud_option(
                            int(input_data_analysis_comment_word_cloud_top_num.value))
                        ).style(echart_css)
                        echart_comment_word_cloud.move(data_analysis_comment_word_cloud_card, 0)
                    ui.button('更新数据', on_click=lambda: update_echart_comment_word_cloud())
            
            data_analysis_integral_card = ui.card()
            with data_analysis_integral_card.style("width:100%;"):
                echart_integral = ui.echart(data_analysis.get_integral_option(
                    "integral", int(config.get("data_analysis", "integral", "top_num")))
                ).style(echart_css)
        
                with ui.row():
                    input_data_analysis_integral_top_num = ui.input(label='Top N个数据', value=config.get("data_analysis", "integral", "top_num"), placeholder='筛选Top N个数据')
                    def update_echart_integral(type):
                        data_analysis_integral_card.remove(0)
                        echart_integral = ui.echart(data_analysis.get_integral_option(
                            type,
                            int(input_data_analysis_integral_top_num.value))
                        ).style(echart_css)
                        echart_integral.move(data_analysis_integral_card, 0)
                    ui.button('获取积分榜', on_click=lambda: update_echart_integral('integral'))
                    ui.button('获取观看榜', on_click=lambda: update_echart_integral('view_num'))
                    ui.button('获取签到榜', on_click=lambda: update_echart_integral('sign_num'))
                    ui.button('获取金额榜', on_click=lambda: update_echart_integral('total_price'))
            data_analysis_gift_card = ui.card()
            with data_analysis_gift_card.style("width:100%;"):
                echart_gift = ui.echart(data_analysis.get_gift_option(int(config.get("data_analysis", "gift", "top_num")))).style(echart_css)
        
                with ui.row():
                    input_data_analysis_gift_top_num = ui.input(label='Top N个数据', value=config.get("data_analysis", "gift", "top_num"), placeholder='筛选Top N个数据')
                    def update_echart_gift():
                        data_analysis_gift_card.remove(0)
                        echart_gift = ui.echart(data_analysis.get_gift_option(
                            int(input_data_analysis_gift_top_num.value))
                        ).style(echart_css)
                        echart_gift.move(data_analysis_gift_card, 0)
                    ui.button('更新数据', on_click=lambda: update_echart_gift())
        with ui.tab_panel(web_page).style(tab_panel_css):
            with ui.card().style(card_css):
                ui.label("webui配置")
                with ui.row():
                    input_webui_title = ui.input(label='标题', placeholder='webui的标题', value=config.get("webui", "title")).style("width:250px;")
                    input_webui_ip = ui.input(label='IP地址', placeholder='webui监听的IP地址', value=config.get("webui", "ip")).style("width:150px;")
                    input_webui_port = ui.input(label='端口', placeholder='webui监听的端口', value=config.get("webui", "port")).style("width:100px;")
                    switch_webui_auto_run = ui.switch('自动运行', value=config.get("webui", "auto_run")).style(switch_internal_css)
            
            with ui.card().style(card_css):
                ui.label("本地路径指定URL路径访问")
                with ui.row():
                    input_webui_local_dir_to_endpoint_index = ui.input(label='配置索引', value="", placeholder='配置组的排序号，就是说第一个组是1，第二个组是2，以此类推。请填写纯正整数')
                    button_webui_local_dir_to_endpoint_add = ui.button('增加配置组', on_click=webui_local_dir_to_endpoint_add, color=button_internal_color).style(button_internal_css)
                    button_webui_local_dir_to_endpoint_del = ui.button('删除配置组', on_click=lambda: webui_local_dir_to_endpoint_del(input_webui_local_dir_to_endpoint_index.value), color=button_internal_color).style(button_internal_css)
                
                with ui.row():
                    switch_webui_local_dir_to_endpoint_enable = ui.switch('启用', value=config.get("webui", "local_dir_to_endpoint", "enable")).style(switch_internal_css)
                with ui.row():
                    webui_local_dir_to_endpoint_config_var = {}
                    webui_local_dir_to_endpoint_config_card = ui.card()
                    for index, webui_local_dir_to_endpoint_config in enumerate(config.get("webui", "local_dir_to_endpoint", "config")):
                        with webui_local_dir_to_endpoint_config_card.style(card_css):
                            with ui.row():
                                webui_local_dir_to_endpoint_config_var[str(2 * index)] = ui.input(label=f"URL路径#{index + 1}", value=webui_local_dir_to_endpoint_config["url_path"], placeholder='以斜杠（"/"）开始的字符串，它标识了应该为客户端提供文件的URL路径').style("width:200px;")
                                webui_local_dir_to_endpoint_config_var[str(2 * index + 1)] = ui.input(label=f"本地文件夹路径#{index + 1}", value=webui_local_dir_to_endpoint_config["local_dir"], placeholder='本地文件夹路径，建议相对路径，最好是项目内部的路径').style("width:300px;")
                               

            with ui.card().style(card_css):
                ui.label("CSS")
                with ui.row():
                    theme_list = config.get("webui", "theme", "list").keys()
                    data_json = {}
                    for line in theme_list:
                        data_json[line] = line
                    select_webui_theme_choose = ui.select(
                        label='主题', 
                        options=data_json, 
                        value=config.get("webui", "theme", "choose")
                    )

            with ui.card().style(card_css):
                ui.label("配置模板")
                with ui.row():
                    # 获取指定路径下指定拓展名的文件名列表
                    config_template_paths = common.get_specify_extension_names_in_folder("./", "*.json")
                    data_json = {}
                    for line in config_template_paths:
                        data_json[line] = line
                    select_config_template_path = ui.select(
                        label='配置模板路径', 
                        options=data_json, 
                        value="",
                        with_input=True,
                        new_value_mode='add-unique',
                        clearable=True
                    )

                    button_config_template_save = ui.button('保存webui配置到文件', on_click=lambda: config_template_save(select_config_template_path.value), color=button_internal_color).style(button_internal_css)
                    button_config_template_load = ui.button('读取模板到本地（慎点）', on_click=lambda: config_template_load(select_config_template_path.value), color=button_internal_color).style(button_internal_css)               






    with ui.grid(columns=6).style("position: fixed; bottom: 10px; text-align: center;"):
        button_save = ui.button('保存配置', on_click=lambda: save_config(), color=button_bottom_color).style(button_bottom_css).tooltip("保存webui的配置到本地文件，有些配置保存后需要重启生效")
        button_run = ui.button('一键运行', on_click=lambda: run_external_program(), color=button_bottom_color).style(button_bottom_css).tooltip("运行main.py")
        # 创建一个按钮，用于停止正在运行的程序
        button_stop = ui.button("停止运行", on_click=lambda: stop_external_program(), color=button_bottom_color).style(button_bottom_css).tooltip("停止运行main.py")
        # button_stop.enabled = False  # 初始状态下停止按钮禁用
        button_restart = ui.button('重启', on_click=lambda: restart_application(), color=button_bottom_color).style(button_bottom_css).tooltip("停止运行main.py并重启webui")
        # factory_btn = ui.button('恢复出厂配置', on_click=lambda: factory(), color=button_bottom_color).style(tab_panel_css)

    with ui.row().style("position:fixed; bottom: 20px; right: 20px;"):
        ui.button('⇧', on_click=lambda: scroll_to_top(), color=button_bottom_color).style(button_bottom_css)

    # 是否启用自动运行功能
    if config.get("webui", "auto_run"):
        logger.info("自动运行 已启用")
        run_external_program(type="api")

# 发送心跳包
ui.timer(9 * 60, lambda: common.send_heartbeat())

# 是否启用登录功能（暂不合理）
        
# 跳转到功能页
goto_func_page()


ui.run(host=webui_ip, port=webui_port, title=webui_title, favicon="./ui/favicon-64.ico", language="zh-CN", dark=False, reload=False)
# ui.run(host=webui_ip, port=webui_port, title=webui_title, favicon="./ui/favicon-64.ico", language="zh-CN", dark=False, reload=False,
#        ssl_certfile="F:\\FunASR_WS\\cert.pem", ssl_keyfile="F:\\FunASR_WS\\key.pem")