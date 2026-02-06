from typing import Any, Dict, Optional, Type, TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from gsuid_core.utils.database.base_models import BaseModel, with_session
from gsuid_core.utils.database.models import Subscribe

T_RoverSubscribe = TypeVar("T_RoverSubscribe", bound="RoverSubscribe")
T_WavesSubscribeReader = TypeVar("T_WavesSubscribeReader", bound="WavesSubscribeReader")


class RoverSubscribe(BaseModel, table=True):
    """群组Bot记录表

    自动记录每个群最后使用的bot_self_id
    当检测到bot变化时，自动更新该群所有订阅的bot_id
    """

    __tablename__ = "RoverSubscribe"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    group_id: str = Field(default="", title="群组ID", unique=True)
    bot_self_id: str = Field(default="", title="BotSelfID")
    updated_at: Optional[int] = Field(default=None, title="最后更新时间")

    @classmethod
    @with_session
    async def check_and_update_bot(
        cls: Type[T_RoverSubscribe],
        session: AsyncSession,
        group_id: str,
        bot_self_id: str,
    ) -> bool:
        """检查并更新群组的bot_self_id

        如果bot_self_id发生变化，自动更新该群所有订阅的bot_self_id

        Args:
            group_id: 群组ID
            bot_self_id: 新的bot_self_id

        Returns:
            bool: 是否发生了bot变更
        """
        import time
        from gsuid_core.logger import logger

        current_time = int(time.time())

        logger.debug(
            f"[RoverSubscribe] check_and_update_bot 被调用: group_id={group_id}, bot_self_id={bot_self_id}"
        )

        # 查询现有记录
        sql = select(cls).where(cls.group_id == group_id)
        result = await session.execute(sql)
        existing = result.scalars().first()

        if existing:
            logger.debug(
                f"[RoverSubscribe] 找到现有记录: group_id={group_id}, existing.bot_self_id={existing.bot_self_id}, new_bot_self_id={bot_self_id}"
            )
            # 检查bot是否变化
            if existing.bot_self_id != bot_self_id:
                old_bot_self_id = existing.bot_self_id
                logger.info(
                    f"[RoverSign订阅] 检测到群 {group_id} 的bot变更: {old_bot_self_id} -> {bot_self_id}"
                )

                # 更新所有订阅的bot_self_id
                update_sql = (
                    update(Subscribe)
                    .where(
                        and_(
                            col(Subscribe.group_id) == group_id,
                            col(Subscribe.bot_self_id) == old_bot_self_id,
                        )
                    )
                    .values(bot_self_id=bot_self_id)
                )
                update_result = await session.execute(update_sql)

                if update_result.rowcount > 0:
                    logger.info(
                        f"[RoverSign订阅] 已自动更新 {update_result.rowcount} 条订阅记录的bot_self_id"
                    )

                # 更新记录
                existing.bot_self_id = bot_self_id
                existing.updated_at = current_time
                session.add(existing)

                return True
            else:
                # bot未变化，只更新时间
                existing.updated_at = current_time
                session.add(existing)
                return False
        else:
            logger.debug(
                f"[RoverSubscribe] 未找到记录，创建新记录: group_id={group_id}, bot_self_id={bot_self_id}"
            )
            # 首次记录
            new_record = cls(
                bot_id="onebot",
                user_id="",
                group_id=group_id,
                bot_self_id=bot_self_id,
                updated_at=current_time,
            )
            session.add(new_record)
            logger.debug(f"[RoverSign订阅] 首次记录群 {group_id} 的bot: {bot_self_id}")
            return False

    @classmethod
    @with_session
    async def get_group_bot(
        cls: Type[T_RoverSubscribe],
        session: AsyncSession,
        group_id: str,
    ) -> Optional[str]:
        """获取群组当前的bot_self_id"""
        sql = select(cls).where(cls.group_id == group_id)
        result = await session.execute(sql)
        record = result.scalars().first()
        return record.bot_self_id if record else None


class WavesSubscribeReader(BaseModel, table=True):
    """读取 XutheringWavesUID 的 WavesSubscribe 表（只读）

    与 XutheringWavesUID 共用同一张表，避免直接依赖
    """

    __tablename__ = "WavesSubscribe"
    __table_args__: Dict[str, Any] = {"extend_existing": True}

    group_id: str = Field(default="", title="群组ID", unique=True)
    bot_self_id: str = Field(default="", title="BotSelfID")
    updated_at: Optional[int] = Field(default=None, title="最后更新时间")

    @classmethod
    @with_session
    async def get_group_bot(
        cls: Type[T_WavesSubscribeReader],
        session: AsyncSession,
        group_id: str,
    ) -> Optional[str]:
        """获取群组当前的bot_self_id"""
        sql = select(cls).where(cls.group_id == group_id)
        result = await session.execute(sql)
        record = result.scalars().first()
        return record.bot_self_id if record else None
