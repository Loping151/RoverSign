from typing import Any, Dict, Optional, Type, TypeVar

from sqlmodel import Field, col, select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from gsuid_core.utils.database.base_models import BaseModel, with_read_session, with_session
from gsuid_core.utils.database.models import Subscribe

from ._lock import with_lock

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
    @with_read_session
    async def _binding(
        cls: Type[T_RoverSubscribe],
        session: AsyncSession,
        group_id: str,
    ) -> tuple[str, str] | None:
        sql = select(cls).where(cls.group_id == group_id)
        record = (await session.execute(sql)).scalars().first()
        if record is None:
            return None
        return record.bot_id, record.bot_self_id

    @classmethod
    async def check_and_update_bot(
        cls: Type[T_RoverSubscribe],
        group_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        if await cls._binding(group_id) == (bot_id, bot_self_id):
            return False
        return await cls._apply_bot_change(group_id, bot_id, bot_self_id)

    @classmethod
    @with_lock
    @with_session
    async def _apply_bot_change(
        cls: Type[T_RoverSubscribe],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
        bot_self_id: str,
    ) -> bool:
        """检查并更新群组的bot_self_id

        如果bot_self_id发生变化，自动更新该群所有订阅的bot_self_id

        Args:
            group_id: 群组ID
            bot_id: 平台 bot_id（onebot / qqgroup / ...）
            bot_self_id: 新的bot_self_id

        Returns:
            bool: 是否发生了bot变更
        """
        import time
        from gsuid_core.logger import logger

        current_time = int(time.time())

        logger.debug(
            f"[库洛签到·订阅] check_and_update_bot 被调用: group_id={group_id}, bot_id={bot_id}, bot_self_id={bot_self_id}"
        )

        # 查询现有记录
        sql = select(cls).where(cls.group_id == group_id)
        result = await session.execute(sql)
        existing = result.scalars().first()

        if existing:
            logger.debug(
                f"[库洛签到·订阅] 找到现有记录: group_id={group_id}, existing.bot_self_id={existing.bot_self_id}, new_bot_self_id={bot_self_id}"
            )
            # 检查bot是否变化
            if existing.bot_self_id != bot_self_id:
                old_bot_self_id = existing.bot_self_id
                logger.info(
                    f"[库洛签到·订阅] 检测到群 {group_id} 的bot变更: {old_bot_self_id} -> {bot_self_id}"
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
                        f"[库洛签到·订阅] 已自动更新 {update_result.rowcount} 条订阅记录的bot_self_id"
                    )

                # 更新记录
                existing.bot_id = bot_id
                existing.bot_self_id = bot_self_id
                existing.updated_at = current_time
                session.add(existing)

                return True
            else:
                # bot未变化，只更新时间和平台标识
                existing.bot_id = bot_id
                existing.updated_at = current_time
                session.add(existing)
                return False
        else:
            logger.debug(
                f"[库洛签到·订阅] 未找到记录，创建新记录: group_id={group_id}, bot_self_id={bot_self_id}"
            )
            # 使用 INSERT ... ON CONFLICT DO UPDATE 原子操作，避免并发 INSERT 竞态导致索引损坏
            stmt = sqlite_insert(cls).values(
                bot_id=bot_id,
                user_id="",
                group_id=group_id,
                bot_self_id=bot_self_id,
                updated_at=current_time,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["group_id"],
                set_={
                    "bot_id": stmt.excluded.bot_id,
                    "bot_self_id": stmt.excluded.bot_self_id,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            logger.debug(f"[库洛签到·订阅] 首次记录群 {group_id} 的bot: {bot_self_id}")
            return False

    @classmethod
    @with_read_session
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
    @with_read_session
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
