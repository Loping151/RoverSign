import asyncio
from functools import wraps

from gsuid_core.logger import logger

_DB_WRITE_LOCK = asyncio.Lock()
_DB_LOCK_TIMEOUT = 30  # 数据库锁超时（秒）


def with_lock(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            await asyncio.wait_for(_DB_WRITE_LOCK.acquire(), timeout=_DB_LOCK_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[RS DB] 获取数据库写锁超时（{_DB_LOCK_TIMEOUT}s），跳过: {func.__name__}")
            return None
        try:
            return await func(*args, **kwargs)
        finally:
            _DB_WRITE_LOCK.release()

    return wrapper
