from functools import wraps


def with_lock(func):
    """保留装饰器接口兼容性，不再加锁。

    数据库写入的并发安全由 with_session（独立 session + 事务）保障，
    不同用户操作不同行无竞争，同一用户的签到流程本身是串行的。
    原全局锁在高并发时超时会导致写入被静默跳过，反而丢数据。
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper
