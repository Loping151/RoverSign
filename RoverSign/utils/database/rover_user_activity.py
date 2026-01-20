from typing import Any, Dict, Optional, Type, TypeVar

from sqlmodel import Field, select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from gsuid_core.utils.database.base_models import BaseBotIDModel, with_session

T_RoverUserActivity = TypeVar("T_RoverUserActivity", bound="RoverUserActivity")


class RoverUserActivity(BaseBotIDModel, table=True):
    """RoverSign 用户活跃度记录表

    记录每个用户（user_id + bot_id + bot_self_id）的最后活跃时间
    通过 hook 机制自动更新，用于判断用户活跃度
    """

    __tablename__ = "RoverUserActivity"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    user_id: str = Field(default="", title="用户ID")
    bot_self_id: str = Field(default="", title="机器人自身ID")
    last_active_time: Optional[int] = Field(default=None, title="最后活跃时间")

    @classmethod
    @with_session
    async def update_user_activity(
        cls: Type[T_RoverUserActivity],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        """更新用户活跃时间

        如果记录不存在则创建，存在则更新时间

        Args:
            user_id: 用户ID
            bot_id: 机器人ID
            bot_self_id: 机器人自身ID

        Returns:
            bool: 是否成功更新
        """
        import time

        current_time = int(time.time())

        # 查询现有记录
        sql = select(cls).where(
            and_(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                cls.bot_self_id == bot_self_id,
            )
        )
        result = await session.execute(sql)
        existing = result.scalars().first()

        if existing:
            # 更新时间
            existing.last_active_time = current_time
            session.add(existing)
        else:
            # 创建新记录
            new_record = cls(
                user_id=user_id,
                bot_id=bot_id,
                bot_self_id=bot_self_id,
                last_active_time=current_time,
            )
            session.add(new_record)

        return True

    @classmethod
    @with_session
    async def get_user_last_active_time(
        cls: Type[T_RoverUserActivity],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> Optional[int]:
        """获取用户最后活跃时间

        Args:
            user_id: 用户ID
            bot_id: 机器人ID
            bot_self_id: 机器人自身ID

        Returns:
            Optional[int]: 最后活跃时间戳，不存在返回 None
        """
        sql = select(cls).where(
            and_(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                cls.bot_self_id == bot_self_id,
            )
        )
        result = await session.execute(sql)
        record = result.scalars().first()
        return record.last_active_time if record else None

    @classmethod
    @with_session
    async def get_active_user_count(
        cls: Type[T_RoverUserActivity],
        session: AsyncSession,
        active_days: int,
    ) -> int:
        """获取活跃用户数量

        Args:
            active_days: 活跃认定天数

        Returns:
            int: 活跃用户数量
        """
        import time

        current_time = int(time.time())
        threshold_time = current_time - (active_days * 24 * 60 * 60)

        sql = select(cls).where(
            and_(
                cls.last_active_time.is_not(None),
                cls.last_active_time >= threshold_time,
            )
        )

        result = await session.execute(sql)
        data = result.scalars().all()
        return len(data)

    @classmethod
    @with_session
    async def is_user_active(
        cls: Type[T_RoverUserActivity],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        bot_self_id: str,
        active_days: int,
    ) -> bool:
        """判断用户是否活跃

        Args:
            user_id: 用户ID
            bot_id: 机器人ID
            bot_self_id: 机器人自身ID
            active_days: 活跃认定天数

        Returns:
            bool: 是否活跃
        """
        import time

        last_active_time = await cls.get_user_last_active_time(user_id, bot_id, bot_self_id)
        if last_active_time is None:
            return False

        current_time = int(time.time())
        threshold_time = current_time - (active_days * 24 * 60 * 60)

        return last_active_time >= threshold_time
