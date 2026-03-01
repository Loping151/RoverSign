from enum import Enum
from typing import Literal


class BoardcastTypeEnum(str, Enum):
    """订阅类型"""

    SIGN_RESULT = "订阅鸣潮签到结果"
    SIGN_WAVES = "订阅鸣潮签到"


BoardcastType = Literal[
    BoardcastTypeEnum.SIGN_RESULT,
    BoardcastTypeEnum.SIGN_WAVES,
]


class TokenStatus(str, Enum):
    """token状态"""

    UNBOUND = "未绑定"
    VALID = "有效"
    INVALID = "登录已过期"
    ERROR = "错误"
    NOT_REGISTERED = "未注册库街区"
    UNKNOWN = "未知"
    BANNED = "IP封禁"


TokenType = Literal[
    TokenStatus.UNBOUND,
    TokenStatus.VALID,
    TokenStatus.INVALID,
    TokenStatus.ERROR,
    TokenStatus.NOT_REGISTERED,
    TokenStatus.UNKNOWN,
    TokenStatus.BANNED,
]
