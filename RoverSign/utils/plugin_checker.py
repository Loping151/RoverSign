import inspect
from typing import Optional

from gsuid_core.logger import logger


def is_from_plugin(plugin_name: str = "RoverSign") -> bool:
    """检查当前调用是否来自指定插件"""
    current_plugin = get_current_plugin()
    result = current_plugin == plugin_name

    if result:
        logger.debug(f"[RS PluginChecker] 调用来自插件 {plugin_name}")

    return result


def get_current_plugin() -> Optional[str]:
    """获取当前执行的插件名称
    Returns:
        Optional[str]: 插件名称，如果不在插件中则返回 None
    """
    frame = inspect.currentframe()

    # 需要跳过的工具文件
    skip_files = ["plugin_checker.py", "bot_send_hook.py"]
    all_plugins = []  # 记录所有遇到的插件

    try:
        frame = frame.f_back

        while frame:
            frame_info = inspect.getframeinfo(frame)
            file_path = frame_info.filename

            # 检查是否在 plugins 目录中
            if "/plugins/" in file_path:
                parts = file_path.split("/plugins/")
                if len(parts) >= 2:
                    plugin_path = parts[1]
                    plugin_name = plugin_path.split("/")[0]
                    # 只记录非工具文件的插件
                    if not any(skip_file in file_path for skip_file in skip_files):
                        all_plugins.append(plugin_name)
            elif "\\plugins\\" in file_path:
                parts = file_path.split("\\plugins\\")
                if len(parts) >= 2:
                    plugin_path = parts[1]
                    plugin_name = plugin_path.split("\\")[0]
                    if not any(skip_file in file_path for skip_file in skip_files):
                        all_plugins.append(plugin_name)

            frame = frame.f_back

        if all_plugins:
            result = all_plugins[-1]  # 最后一个就是离 hook 调用最近的
            logger.debug(f"[RS PluginChecker] 找到的插件列表: {all_plugins}, 返回: {result}")
            return result
    finally:
        del frame

    logger.debug(f"[RS PluginChecker] 未找到插件来源")
    return None


def is_from_rover_plugin() -> bool:
    """快捷方法：检查是否来自 RoverSign 插件"""
    return is_from_plugin("RoverSign")
