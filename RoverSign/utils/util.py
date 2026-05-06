import asyncio
import random
import string
import time
from datetime import datetime, timedelta
from functools import wraps

import httpx

from gsuid_core.logger import logger


def timed_async_cache(expiration, condition=lambda x: True):
    def decorator(func):
        cache = {}
        locks = {}

        @wraps(func)
        async def wrapper(*args):
            current_time = time.time()
            # 如果是类方法，args[0]是实例，我们获取类名
            if args and hasattr(args[0], "__class__"):
                cache_key = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                cache_key = func.__name__

            # 为每个缓存键创建一个锁
            if cache_key not in locks:
                locks[cache_key] = asyncio.Lock()

            # 检查缓存，如果有效则直接返回
            if cache_key in cache:
                value, timestamp = cache[cache_key]
                if current_time - timestamp < expiration:
                    return value

            # 获取锁以确保并发安全
            async with locks[cache_key]:
                # 双重检查，避免等待锁期间其他协程已经更新了缓存
                if cache_key in cache:
                    value, timestamp = cache[cache_key]
                    if current_time - timestamp < expiration:
                        return value

                # 执行原始函数
                value = await func(*args)
                if condition(value):
                    cache[cache_key] = (value, current_time)
                return value

        return wrapper

    return decorator


# 使用示例
@timed_async_cache(86400)
async def get_public_ip(host="127.127.127.127"):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://event.kurobbs.com/event/ip", timeout=4)
            ip = r.text
            return ip
    except Exception as e:
        logger.error(f"获取kuro ip失败: {e}")
        pass

    # 尝试从 ipify 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.ipify.org/?format=json", timeout=4)
            ip = r.json()["ip"]
            return ip
    except:  # noqa:E722, B001
        pass

    # 尝试从 httpbin.org 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://httpbin.org/ip", timeout=4)
            ip = r.json()["origin"]
            return ip
    except Exception:
        pass

    return host


def generate_random_string(length=32):
    # 定义可能的字符集合
    characters = string.ascii_letters + string.digits + string.punctuation
    # 使用random.choice随机选择字符，并连接成字符串
    random_string = "".join(random.choice(characters) for i in range(length))
    return random_string


def generate_random_ipv6_manual():
    return ":".join([hex(random.randint(0, 0xFFFF))[2:].zfill(4) for _ in range(8)])


def generate_random_ipv4_manual():
    return ".".join([str(random.randint(0, 255)) for _ in range(4)])


def get_today_date():
    today = datetime.now()
    return today.strftime("%Y-%m-%d")


def get_yesterday_date():
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def get_two_days_ago_date():
    two_days_ago = datetime.now() - timedelta(days=2)
    return two_days_ago.strftime("%Y-%m-%d")


def hide_uid(uid, user_pref: str = "") -> str:
    """user_pref: 该 uid 对应 WavesUser.hide_uid_self_value, 由 caller 传入。

    "on" 强制隐藏 / "off" 强制不隐藏 / "" 跟随全局 HideUid。
    """
    from ..roversign_config.roversign_config import RoverSignConfig

    uid_str = str(uid) if uid is not None else ""
    if user_pref == "off":
        return uid_str
    if user_pref != "on":
        if not RoverSignConfig.get_config("HideUid").data:
            return uid_str
    if len(uid_str) < 2:
        return uid_str
    return uid_str[:2] + "*" * 4 + uid_str[-2:]


async def get_hide_uid_pref(uid: str, user_id: str, bot_id: str, game_id=None) -> str:
    """读 WavesUser.hide_uid_self_value, 没绑定就回空 (走全局 HideUid)。"""

    from .database.models import WavesUser

    try:
        user = await WavesUser.select_waves_user(
            uid,
            user_id,
            bot_id,
            game_id=game_id,
        )
        return user.hide_uid_self_value if user else ""
    except Exception:
        return ""
