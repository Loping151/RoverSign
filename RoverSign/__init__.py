"""init"""

import asyncio

from gsuid_core.sv import Plugins
from gsuid_core.logger import logger
from gsuid_core.server import on_core_shutdown

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

    # ===== 活跃度批量写入缓冲 =====
    _activity_buffer: dict[str, tuple[str, str, str]] = {}
    _FLUSH_INTERVAL = 60

    async def _flush_activity_buffer():
        if not _activity_buffer:
            return
        pending = dict(_activity_buffer)
        _activity_buffer.clear()
        for key, (user_id, bot_id, bot_self_id) in pending.items():
            try:
                await RoverUserActivity.update_user_activity(user_id, bot_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[RS] 批量活跃度写入失败: {e}")

    _shutdown_event = asyncio.Event()

    async def _activity_flush_loop():
        while not _shutdown_event.is_set():
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=_FLUSH_INTERVAL)
                break  # shutdown signaled
            except asyncio.TimeoutError:
                pass
            try:
                await _flush_activity_buffer()
            except Exception as e:
                logger.warning(f"[RS] 活跃度刷写循环异常: {e}")

    _flush_task = asyncio.get_event_loop().create_task(_activity_flush_loop())

    @on_core_shutdown
    async def _flush_on_shutdown():
        logger.info("[RoverSign] 退出前停止活跃度刷写循环...")
        _shutdown_event.set()
        try:
            await asyncio.wait_for(_flush_task, timeout=5)
        except asyncio.TimeoutError:
            _flush_task.cancel()
        logger.info("[RoverSign] 刷写活跃度缓冲区...")
        await _flush_activity_buffer()
        logger.info("[RoverSign] 活跃度缓冲区刷写完成")

    async def rover_bot_check_hook(group_id: str, bot_self_id: str):
        """RoverSign 的 bot 检测 hook"""
        logger.debug(f"[RS Hook] bot_check_hook 被调用: group_id={group_id}, bot_self_id={bot_self_id}")

        if group_id:
            try:
                await RoverSubscribe.check_and_update_bot(group_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[RS Hook] Bot检测失败: {e}")

    async def rover_user_activity_hook(user_id: str, bot_id: str, bot_self_id: str):
        """RoverSign 的用户活跃度 hook - 写入缓冲区，定时批量刷写"""
        if not is_from_rover_plugin():
            return
        if not user_id:
            return
        _activity_buffer[f"{user_id}:{bot_id}:{bot_self_id}"] = (user_id, bot_id, bot_self_id)

    # 安装 hooks 并注册
    logger.info("[RoverSign] 开始安装和注册 hooks...")
    install_bot_hooks()
    register_target_send_hook(rover_bot_check_hook)
    register_user_activity_hook(rover_user_activity_hook)
    logger.info("[RoverSign] Hooks 安装和注册完成")

except ImportError as e:
    logger.warning(f"[RoverSign] 无法导入共享 hook 机制: {e}，跳过 hook 安装")
except Exception as e:
    logger.error(f"[RoverSign] 导入 hook 机制时发生错误: {e}，跳过 hook 安装", exc_info=True)
