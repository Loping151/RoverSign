from typing import Callable, Optional
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
import sys


if not hasattr(sys, '_gs_bot_hook_managers'):
    sys._gs_bot_hook_managers = {}
_plugin_hook_managers = sys._gs_bot_hook_managers


class PluginHookManager:
    """插件 hook 管理器"""

    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self.target_send_hooks: list[Callable] = []
        self.user_activity_hooks: list[Callable] = []

    def register_target_send_hook(self, func: Callable):
        """注册 target_send 方法 hook"""
        existing = [h for h in self.target_send_hooks if h.__name__ == func.__name__]
        if existing:
            self.target_send_hooks[:] = [h for h in self.target_send_hooks if h.__name__ != func.__name__]
            logger.debug(f"[{self.plugin_name} BotHook] 更新 target_send hook: {func.__name__}")
        else:
            logger.debug(f"[{self.plugin_name} BotHook] 注册 target_send hook: {func.__name__}")
        self.target_send_hooks.append(func)

    def register_user_activity_hook(self, func: Callable):
        """注册用户活跃度 hook"""
        existing = [h for h in self.user_activity_hooks if h.__name__ == func.__name__]
        if existing:
            self.user_activity_hooks[:] = [h for h in self.user_activity_hooks if h.__name__ != func.__name__]
            logger.debug(f"[{self.plugin_name} BotHook] 更新 user_activity hook: {func.__name__}")
        else:
            logger.debug(f"[{self.plugin_name} BotHook] 注册 user_activity hook: {func.__name__}")
        self.user_activity_hooks.append(func)


def get_or_create_hook_manager(plugin_name: str) -> PluginHookManager:
    """获取或创建插件的 hook 管理器"""
    if plugin_name not in _plugin_hook_managers:
        _plugin_hook_managers[plugin_name] = PluginHookManager(plugin_name)
        logger.debug(f"[BotHook] 创建新的插件管理器: {plugin_name}, 当前管理器列表: {list(_plugin_hook_managers.keys())}")
    else:
        logger.debug(f"[BotHook] 复用已存在的插件管理器: {plugin_name}")
    return _plugin_hook_managers[plugin_name]


_rs_manager = get_or_create_hook_manager("RS")


def register_target_send_hook(func: Callable):
    """注册 target_send 方法 hook"""
    _rs_manager.register_target_send_hook(func)


def register_user_activity_hook(func: Callable):
    """注册用户活跃度 hook"""
    _rs_manager.register_user_activity_hook(func)


async def _call_all_target_send_hooks(
    target_type: str,
    target_id: Optional[str],
    bot_id: str,
    bot_self_id: str,
):
    """调用所有插件的 target_send hooks"""
    group_id = target_id if target_type == "group" else None
    if not group_id:
        return

    for plugin_name, manager in _plugin_hook_managers.items():
        if not manager.target_send_hooks:
            continue

        logger.debug(f"[{plugin_name} BotHook] 调用 {len(manager.target_send_hooks)} 个 target_send hooks, group_id={group_id}")

        for hook in manager.target_send_hooks:
            try:
                logger.debug(f"[{plugin_name} BotHook] 执行 hook: {hook.__name__}, group_id={group_id}")
                await hook(group_id, bot_self_id)
            except Exception as e:
                logger.warning(f"[{plugin_name} BotHook] target_send hook {hook.__name__} 执行失败: {e}")


async def _call_all_user_activity_hooks(user_id: Optional[str], bot_id: str, bot_self_id: str):
    """调用所有插件的用户活跃度 hooks"""
    if not user_id:
        return

    logger.debug(f"[BotHook] 当前已注册的插件管理器: {list(_plugin_hook_managers.keys())}")

    for plugin_name, manager in _plugin_hook_managers.items():
        logger.debug(f"[BotHook] 插件 {plugin_name} 有 {len(manager.user_activity_hooks)} 个 user_activity_hooks")

        if not manager.user_activity_hooks:
            continue

        logger.debug(f"[{plugin_name} BotHook] 调用 {len(manager.user_activity_hooks)} 个 user_activity hooks, user_id={user_id}")

        for hook in manager.user_activity_hooks:
            try:
                logger.debug(f"[{plugin_name} BotHook] 执行 hook: {hook.__name__}, user_id={user_id}")
                try:
                    await hook(user_id, bot_id, bot_self_id)
                except TypeError:
                    await hook(user_id, bot_id)
            except Exception as e:
                logger.warning(f"[{plugin_name} BotHook] user_activity hook {hook.__name__} 执行失败: {e}")


def install_bot_hooks():
    """
    通过 Monkey Patch 的方式拦截 Bot.send 和 Bot.target_send 方法
    只会安装一次，所有插件的 hooks 都会被调用
    """
    if hasattr(Bot, "_bot_hooks_installed"):
        logger.debug("[BotHook] Bot hooks 已经安装，跳过")
        return

    original_send = Bot.send
    original_target_send = Bot.target_send

    # 包装 send 方法
    async def hooked_send(self, *args, **kwargs):
        # 调用 hooks
        user_id = getattr(self.ev, "user_id", None) if hasattr(self, "ev") else None
        bot_id = getattr(self, "bot_id", "") if hasattr(self, "bot_id") else ""
        bot_self_id = getattr(self, "bot_self_id", "") if hasattr(self, "bot_self_id") else ""

        # 调用所有插件的用户活跃度 hooks
        await _call_all_user_activity_hooks(user_id, bot_id, bot_self_id)

        # 调用原始方法
        return await original_send(self, *args, **kwargs)

    # 包装 target_send 方法
    async def hooked_target_send(self, *args, **kwargs):
        if len(args) >= 5:
            target_type = args[1]
            target_id = args[2]
            bot_id = args[3]
            bot_self_id = args[4]

            # 调用所有插件的 target_send hooks
            await _call_all_target_send_hooks(target_type, target_id, bot_id, bot_self_id)

        # 调用原始方法
        return await original_target_send(self, *args, **kwargs)

    # 替换方法
    Bot.send = hooked_send
    Bot.target_send = hooked_target_send
    Bot._bot_hooks_installed = True

    logger.debug("[BotHook] Bot hooks 已安装")
