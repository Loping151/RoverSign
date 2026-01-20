from typing import Callable
from gsuid_core.bot import Bot
from gsuid_core.logger import logger

# 导入中央管理器
from gsuid_core.plugins.XutheringWavesUID.XutheringWavesUID.utils.bot_send_hook import (
    get_or_create_hook_manager,
    install_bot_hooks,
)

# 获取 RoverSign 的 hook 管理器
_rs_manager = get_or_create_hook_manager("RS")


def register_target_send_hook(func: Callable):
    """注册 target_send 方法 hook"""
    _rs_manager.register_target_send_hook(func)


def register_user_activity_hook(func: Callable):
    """注册用户活跃度 hook"""
    _rs_manager.register_user_activity_hook(func)
