import asyncio
from functools import wraps

_DB_WRITE_LOCK = asyncio.Lock()


def with_lock(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with _DB_WRITE_LOCK:
            return await func(*args, **kwargs)

    return wrapper
