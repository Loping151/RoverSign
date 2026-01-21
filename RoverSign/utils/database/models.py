import asyncio
from functools import wraps
from typing import Any, Dict, List, Type, TypeVar, Optional

from sqlmodel import Field, col, select
from sqlalchemy import null, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel as PydanticBaseModel
from gsuid_core.utils.database.startup import exec_list
from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import (
    Bind,
    User,
    BaseIDModel,
    with_session,
)

from ..util import get_today_date
from .rover_user_activity import RoverUserActivity
from .rover_subscribe import RoverSubscribe

exec_list.extend(
    [
        'ALTER TABLE RoverSign ADD COLUMN pgr_uid TEXT DEFAULT ""',
        "ALTER TABLE RoverSign ADD COLUMN pgr_game_sign INTEGER DEFAULT 0",
        "ALTER TABLE WavesUser ADD COLUMN is_login INTEGER DEFAULT 0 NOT NULL",
        "ALTER TABLE WavesUser ADD COLUMN created_time INTEGER",
        "ALTER TABLE WavesUser ADD COLUMN last_used_time INTEGER",
    ]
)

_DB_WRITE_LOCK = asyncio.Lock()


def with_lock(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with _DB_WRITE_LOCK:
            return await func(*args, **kwargs)

    return wrapper


T_WavesBind = TypeVar("T_WavesBind", bound="WavesBind")
T_WavesUser = TypeVar("T_WavesUser", bound="WavesUser")
T_RoverSign = TypeVar("T_RoverSign", bound="RoverSign")


class WavesBind(Bind, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}
    uid: Optional[str] = Field(default=None, title="鸣潮UID")
    pgr_uid: Optional[str] = Field(default=None, title="战双UID")


class WavesUser(User, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}
    cookie: str = Field(default="", title="Cookie")
    uid: str = Field(default=None, title="鸣潮UID")
    record_id: Optional[str] = Field(default=None, title="记录ID")
    platform: str = Field(default="", title="ck平台")
    stamina_bg_value: str = Field(default="", title="体力背景")
    bbs_sign_switch: str = Field(default="off", title="自动社区签到")
    bat: str = Field(default="", title="bat")
    did: str = Field(default="", title="did")
    game_id: int = Field(default=3, title="GameID")
    is_login: bool = Field(default=False, title="是否waves登录")
    created_time: Optional[int] = Field(default=None, title="创建时间")
    last_used_time: Optional[int] = Field(default=None, title="最后使用时间")

    @classmethod
    @with_lock
    @with_session
    async def mark_cookie_invalid(
        cls: Type[T_WavesUser], session: AsyncSession, uid: str, cookie: str, mark: str
    ):
        sql = (
            update(cls)
            .where(col(cls.uid) == uid)
            .where(col(cls.cookie) == cookie)
            .values(status=mark)
        )
        await session.execute(sql)
        return True

    @classmethod
    @with_session
    async def select_cookie(
        cls: Type[T_WavesUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> Optional[str]:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0].cookie if data else None

    @classmethod
    @with_session
    async def select_waves_user(
        cls: Type[T_WavesUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
        game_id: Optional[int] = None,
    ) -> Optional[T_WavesUser]:
        """
        根据user_id、uid、bot_id查询数据
        """
        filters = [
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
        ]
        if game_id is not None:
            filters.append(cls.game_id == game_id)
        sql = select(cls).where(*filters)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def select_data_by_cookie(
        cls: Type[T_WavesUser],
        session: AsyncSession,
        cookie: str,
    ) -> Optional[T_WavesUser]:
        """
        根据cookie查询数据
        """
        sql = select(cls).where(cls.cookie == cookie)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def get_waves_all_user(
        cls: Type[T_WavesUser],
        session: AsyncSession,
    ) -> List[T_WavesUser]:
        """
        获取有cookie的玩家。
        """
        sql = (
            select(cls)
            .where(cls.cookie != null())
            .where(cls.cookie != "")
            .where(cls.user_id != null())
            .where(cls.user_id != "")
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return list(data)

    @classmethod
    @with_session
    async def select_data_by_cookie_and_uid(
        cls: Type[T_WavesUser],
        session: AsyncSession,
        cookie: str,
        uid: str,
        game_id: Optional[int] = None,
    ) -> Optional[T_WavesUser]:
        filters = [cls.cookie == cookie, cls.uid == uid]
        if game_id is not None:
            filters.append(cls.game_id == game_id)
        sql = select(cls).where(*filters)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def get_active_waves_user(
        cls: Type[T_WavesUser],
        session: AsyncSession,
        active_days: int,
    ) -> List[T_WavesUser]:
        """
        获取活跃用户（在指定天数内有使用记录）

        Args:
            active_days: 活跃认定天数

        Returns:
            活跃用户列表
        """
        import time

        current_time = int(time.time())
        threshold_time = current_time - (active_days * 24 * 60 * 60)

        sql = (
            select(cls)
            .where(cls.cookie != null())
            .where(cls.cookie != "")
            .where(cls.user_id != null())
            .where(cls.user_id != "")
            .where(cls.last_used_time != null())
            .where(cls.last_used_time >= threshold_time)
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return list(data)

    @classmethod
    @with_lock
    @with_session
    async def update_last_used_time(
        cls,
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
        game_id: Optional[int] = None,
    ):
        """更新最后使用时间，如果创建时间为空则同时设置创建时间

        会更新所有具有相同 uid 和 cookie 的记录
        """
        import time

        current_time = int(time.time())

        # 先查询当前用户获取 cookie
        filters = [
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
        ]
        if game_id is not None:
            filters.append(cls.game_id == game_id)

        result = await session.execute(select(cls).where(*filters))
        user = result.scalars().first()

        if user and user.cookie:
            # 更新所有具有相同 user_id 和 cookie 的记录
            all_users_result = await session.execute(
                select(cls).where(
                    cls.user_id == user_id,
                    cls.cookie == user.cookie,
                )
            )
            all_users = all_users_result.scalars().all()

            # 批量更新
            for u in all_users:
                u.last_used_time = current_time
                if u.created_time is None:
                    u.created_time = current_time

            return True
        return False


class RoverSignData(PydanticBaseModel):
    uid: str  # 鸣潮UID
    pgr_uid: Optional[str] = None  # 战双UID
    date: Optional[str] = None  # 签到日期
    game_sign: Optional[int] = None  # 游戏签到（鸣潮）
    pgr_game_sign: Optional[int] = None  # 游戏签到（战双）
    bbs_sign: Optional[int] = None  # 社区签到
    bbs_detail: Optional[int] = None  # 社区浏览
    bbs_like: Optional[int] = None  # 社区点赞
    bbs_share: Optional[int] = None  # 社区分享

    @classmethod
    def build(cls, uid: str, pgr_uid: Optional[str] = None):
        date = get_today_date()
        return cls(uid=uid, pgr_uid=pgr_uid, date=date)

    @classmethod
    def build_game_sign(cls, uid: str):
        return cls(uid=uid, game_sign=1)

    @classmethod
    def build_pgr_game_sign(cls, uid: str):
        return cls(uid=uid, pgr_game_sign=1)

    @classmethod
    def build_bbs_sign(
        cls,
        uid: str,
    ):
        return cls(
            uid=uid,
            bbs_sign=0,
            bbs_detail=0,
            bbs_like=0,
            bbs_share=0,
        )


class RoverSign(BaseIDModel, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}
    uid: str = Field(title="鸣潮UID")
    pgr_uid: Optional[str] = Field(default=None, title="战双UID")
    game_sign: int = Field(default=0, title="游戏签到（鸣潮）")
    pgr_game_sign: int = Field(default=0, title="游戏签到（战双）")
    bbs_sign: int = Field(default=0, title="社区签到")
    bbs_detail: int = Field(default=0, title="社区浏览")
    bbs_like: int = Field(default=0, title="社区点赞")
    bbs_share: int = Field(default=0, title="社区分享")
    date: str = Field(default=get_today_date(), title="签到日期")

    @classmethod
    async def _find_sign_record(
        cls: Type[T_RoverSign],
        session: AsyncSession,
        uid: str,
        date: str,
    ) -> Optional[T_RoverSign]:
        """查找指定UID和日期的签到记录（内部方法）"""
        query = select(cls).where(cls.uid == uid).where(cls.date == date)
        result = await session.execute(query)
        return result.scalars().first()

    @classmethod
    @with_lock
    @with_session
    async def upsert_rover_sign(
        cls: Type[T_RoverSign],
        session: AsyncSession,
        rover_sign_data: RoverSignData,
    ) -> Optional[T_RoverSign]:
        """
        插入或更新签到数据
        返回更新后的记录或新插入的记录
        """
        if not rover_sign_data.uid:
            return None

        # 确保日期有值
        rover_sign_data.date = rover_sign_data.date or get_today_date()

        # 查询是否存在记录
        record = await cls._find_sign_record(
            session, rover_sign_data.uid, rover_sign_data.date
        )

        if record:
            # 更新已有记录
            for field in [
                "game_sign",
                "pgr_game_sign",
                "bbs_sign",
                "bbs_detail",
                "bbs_like",
                "bbs_share",
            ]:
                value = getattr(rover_sign_data, field)
                if value is not None:
                    setattr(record, field, value)
            # 更新 pgr_uid
            if rover_sign_data.pgr_uid:
                record.pgr_uid = rover_sign_data.pgr_uid
            result = record
        else:
            # 添加新记录 - 直接从Pydantic模型创建SQLModel实例
            result = cls(**rover_sign_data.model_dump())
            session.add(result)

        return result

    @classmethod
    @with_session
    async def get_sign_data(
        cls: Type[T_RoverSign],
        session: AsyncSession,
        uid: str,
        date: Optional[str] = None,
    ) -> Optional[T_RoverSign]:
        """根据UID和日期查询签到数据"""
        date = date or get_today_date()
        return await cls._find_sign_record(session, uid, date)

    @classmethod
    @with_session
    async def get_all_sign_data_by_date(
        cls: Type[T_RoverSign],
        session: AsyncSession,
        date: Optional[str] = None,
    ) -> List[T_RoverSign]:
        """根据日期查询所有签到数据"""
        actual_date = date or get_today_date()
        sql = select(cls).where(cls.date == actual_date)
        result = await session.execute(sql)
        return list(result.scalars().all())

    @classmethod
    @with_lock
    @with_session
    async def clear_sign_record(
        cls: Type[T_RoverSign],
        session: AsyncSession,
        date: str,
    ):
        """清除签到记录"""
        sql = delete(cls).where(getattr(cls, "date") <= date)
        await session.execute(sql)


T_RoverSubscribe = TypeVar("T_RoverSubscribe", bound=RoverSubscribe)


@site.register_admin
class RoverSubscribeAdmin(GsAdminModel):
    """RoverSign 的 Bot-群组绑定管理"""

    pk_name = "group_id"
    page_schema = PageSchema(
        label="RoverSign 发送-群组绑定",
        icon="fa fa-link",
    )  # type: ignore

    model = RoverSubscribe


@site.register_admin
class RoverUserActivityAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="RoverSign 用户活跃度",
        icon="fa fa-clock-o",
    )  # type: ignore

    model = RoverUserActivity
