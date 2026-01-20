"""init"""

from gsuid_core.sv import Plugins
from gsuid_core.logger import logger

Plugins(name="RoverSign", force_prefix=["ww"], allow_empty_prefix=False)

logger.info("[RoverSign] 开始导入 bot_send_hook...")

try:
    from .utils.bot_send_hook import (
        install_bot_hooks,
        register_target_send_hook,
        register_user_activity_hook,
    )
    from .utils.database.models import RoverSubscribe, RoverUserActivity
    from .utils.plugin_checker import is_from_rover_plugin

    logger.info("[RoverSign] bot_send_hook 导入成功")

    async def rover_bot_check_hook(group_id: str, bot_self_id: str):
        """RoverSign 的 bot 检测 hook"""
        logger.debug(f"[RS Hook] bot_check_hook 被调用: group_id={group_id}, bot_self_id={bot_self_id}")

        if group_id:
            try:
                await RoverSubscribe.check_and_update_bot(group_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[RS Hook] Bot检测失败: {e}")

    async def rover_user_activity_hook(user_id: str, bot_id: str, bot_self_id: str):
        """RoverSign 的用户活跃度 hook

        只记录由本插件触发的消息的用户活跃度
        """
        # 检查调用是否来自本插件
        if not is_from_rover_plugin():
            logger.debug(f"[RS Hook] 消息不是来自本插件，跳过活跃度更新: user_id={user_id}")
            return

        logger.debug(f"[RS Hook] user_activity_hook 被调用: user_id={user_id}, bot_id={bot_id}, bot_self_id={bot_self_id}")

        if user_id:
            try:
                await RoverUserActivity.update_user_activity(user_id, bot_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[RS Hook] 用户活跃度更新失败: {e}")

    # 安装 hooks 并注册
    logger.info("[RoverSign] 开始安装和注册 hooks...")
    install_bot_hooks()
    register_target_send_hook(rover_bot_check_hook)
    register_user_activity_hook(rover_user_activity_hook)
    logger.info("[RoverSign] Hooks 安装和注册完成")

    logger.debug("[RoverSign] Bot 消息发送 hook 已注册")
    logger.debug("[RoverSign] 用户活跃度 hook 已注册")
except ImportError as e:
    logger.warning(f"[RoverSign] 无法导入共享 hook 机制: {e}，跳过 hook 安装")
except Exception as e:
    logger.error(f"[RoverSign] 导入 hook 机制时发生错误: {e}，跳过 hook 安装", exc_info=True)
