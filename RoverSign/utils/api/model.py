from typing import List

from pydantic import BaseModel, Field


class DailyData(BaseModel):
    """每日数据"""

    gameId: int
    userId: int
    serverId: str
    roleId: str
    roleName: str
    signInTxt: str
    hasSignIn: bool


class SignInGoodsConfig(BaseModel):
    """签到奖励物品"""

    goodsId: int = 0
    goodsName: str = ""
    goodsNum: int = 0
    goodsUrl: str = ""
    id: int = 0
    isGain: bool = False
    serialNum: int = 0
    signId: int = 0


class SignInInitData(BaseModel):
    """initSignInV2 签到初始化数据"""

    disposableGoodsList: List[SignInGoodsConfig] = Field(default_factory=list)
    eventEndTimes: str = ""
    eventStartTimes: str = ""
    expendGold: int = 0
    expendNum: int = 0
    isSigIn: bool = False
    nowServerTimes: str = ""
    omissionNnm: int = 0
    openNotifica: bool = False
    redirectContent: str = ""
    redirectText: str = ""
    redirectType: int = 0
    repleNum: int = 0
    sigInNum: int = 0
    signInGoodsConfigs: List[SignInGoodsConfig] = Field(default_factory=list)
    signLoopGoodsList: List[SignInGoodsConfig] = Field(default_factory=list)
