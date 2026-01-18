"""init"""

from gsuid_core.sv import Plugins
from gsuid_core.logger import logger

Plugins(name="RoverSign", force_prefix=["ww"], allow_empty_prefix=False)

try:
    from gsuid_core.plugins.XutheringWavesUID.XutheringWavesUID.utils.bot_send_hook import (
        install_bot_hooks,
        register_target_send_hook,
        register_send_hook,
    )
    from .utils.database.models import RoverSubscribe

    async def rover_bot_check_hook(group_id: str, bot_self_id: str):
        """RoverSign 的 bot 检测 hook"""
        logger.debug(f"[RoverSign Hook] bot_check_hook 被调用: group_id={group_id}, bot_self_id={bot_self_id}")

        if group_id:
            try:
                await RoverSubscribe.check_and_update_bot(group_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[RoverSign] Bot检测失败: {e}")

    # 安装 hooks 并注册
    install_bot_hooks()
    register_target_send_hook(rover_bot_check_hook)
    register_send_hook(rover_bot_check_hook)

    logger.info("[RoverSign] Bot 消息发送 hook 已注册")
except ImportError as e:
    logger.warning(f"[RoverSign] 无法导入共享 hook 机制: {e}，跳过 hook 安装")
