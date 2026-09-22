from typing import Any, Dict, List, Set, Type, TypeVar, Optional
from contextvars import ContextVar

from sqlmodel import Field, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from gsuid_core.logger import logger
from gsuid_core.utils.database.base_models import BaseBotIDModel, with_read_session, with_session

from ._lock import with_lock

# 推送期间置位, 用户/群活跃 hook 据此跳过推送自身
PUSH_GUARD: ContextVar[bool] = ContextVar("rover_push_guard", default=False)

T_RoverGroupActivity = TypeVar("T_RoverGroupActivity", bound="RoverGroupActivity")


class RoverGroupActivity(BaseBotIDModel, table=True):
    """群活跃度记录表: 群最后有人使用本插件的时间"""

    __tablename__ = "RoverGroupActivity"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    group_id: str = Field(default="", title="群组ID")
    bot_self_id: str = Field(default="", title="机器人自身ID")
    last_active_time: Optional[int] = Field(default=None, title="最后活跃时间")

    @classmethod
    async def update_group_activity(
        cls: Type[T_RoverGroupActivity],
        group_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        try:
            return await cls._do_update_group_activity(group_id, bot_id, bot_self_id)
        except Exception as e:
            if "malformed" in str(e) or "corrupt" in str(e):
                logger.warning(f"[库洛签到·群活跃度] 数据库损坏，跳过更新: {e}")
                return False
            raise

    @classmethod
    @with_lock
    @with_session
    async def _do_update_group_activity(
        cls: Type[T_RoverGroupActivity],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        import time

        current_time = int(time.time())
        sql = select(cls).where(
            and_(
                cls.group_id == group_id,
                cls.bot_id == bot_id,
                cls.bot_self_id == bot_self_id,
            )
        )
        result = await session.execute(sql)
        existing = result.scalars().first()
        if existing:
            existing.last_active_time = current_time
            session.add(existing)
        else:
            session.add(
                cls(
                    group_id=group_id,
                    bot_id=bot_id,
                    bot_self_id=bot_self_id,
                    last_active_time=current_time,
                )
            )
        return True

    @classmethod
    @with_session
    async def update_many(
        cls: Type[T_RoverGroupActivity],
        _session: AsyncSession,
        rows: List[tuple[str, str, str]],
    ) -> None:
        for group_id, bot_id, bot_self_id in rows:
            await cls._do_update_group_activity(group_id, bot_id, bot_self_id)

    @classmethod
    async def get_active_group_ids(
        cls: Type[T_RoverGroupActivity],
        active_days: int,
    ) -> Set[str]:
        try:
            return await cls._do_get_active_group_ids(active_days)
        except Exception as e:
            if "malformed" in str(e) or "corrupt" in str(e):
                logger.warning(f"[库洛签到·群活跃度] 数据库损坏，返回空活跃群集合: {e}")
                return set()
            raise

    @classmethod
    @with_read_session
    async def _do_get_active_group_ids(
        cls: Type[T_RoverGroupActivity],
        session: AsyncSession,
        active_days: int,
    ) -> Set[str]:
        import time

        threshold_time = int(time.time()) - active_days * 24 * 60 * 60
        sql = select(cls.group_id).where(
            and_(
                cls.last_active_time.is_not(None),
                cls.last_active_time >= threshold_time,
            )
        )
        result = await session.execute(sql)
        return {gid for gid in result.scalars().all() if gid}
