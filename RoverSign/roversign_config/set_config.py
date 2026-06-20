from plugins.RoverSign.RoverSign.utils.constant import BoardcastTypeEnum

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from ..utils.api.api import PGR_GAME_ID
from ..utils.database.models import WavesUser
from ..utils.util import get_hide_uid_pref, hide_uid


async def get_signin_config():
    from .roversign_config import RoverSignConfig

    master = RoverSignConfig.get_config("SigninMaster").data
    signin = RoverSignConfig.get_config("SchedSignin").data
    return master or signin


async def get_bbs_signin_config():
    from .roversign_config import RoverSignConfig

    master = RoverSignConfig.get_config("SigninMaster").data
    signin = RoverSignConfig.get_config("BBSSchedSignin").data

    return master or signin


async def set_config_func(ev: Event, uid: str = "0"):
    config_name = ev.text
    if "开启" in ev.command:
        option = ev.group_id if ev.group_id else "on"
    else:
        option = "off"

    logger.info(f"uid: {uid}, option: {option}, config_name: {config_name}")

    other_msg = ""
    if config_name in ("自动签到", "鸣潮自动签到"):
        if not await get_signin_config():
            return "自动签到功能已禁用!\n"

        # 执行设置
        await WavesUser.update_data_by_uid(
            uid=uid,
            bot_id=ev.bot_id,
            **{
                "sign_switch": option,
                "bbs_sign_switch": option,
            },
        )

        if ev.bot_id == "onebot":
            if option == "off":
                await gs_subscribe.delete_subscribe(
                    "single", BoardcastTypeEnum.SIGN_WAVES, ev
                )
            else:
                await gs_subscribe.add_subscribe(
                    "single", BoardcastTypeEnum.SIGN_WAVES, ev
                )

        if option != "off":
            from .roversign_config import RoverSignConfig

            SIGN_TIME = RoverSignConfig.get_config("SignTime").data
            other_msg = f"😄将于[{SIGN_TIME[0]}:{SIGN_TIME[1]}]点自动为您开始{config_name}"

    else:
        return "该配置项不存在!"

    if option == "on":
        succeed_msg = "开启至私聊消息!"
    elif option == "off":
        succeed_msg = "关闭!"
    else:
        succeed_msg = f"开启至群{option}"

    return f"{config_name}已{succeed_msg}\n{other_msg}"


async def set_pgr_config_func(ev: Event, pgr_uid: str = "0"):
    if ev.text != "战双自动签到":
        return "该配置项不存在!"

    if "开启" in ev.command:
        option = ev.group_id if ev.group_id else "on"
    else:
        option = "off"

    if not await get_signin_config():
        return "自动签到功能已禁用!\n"

    pgr_user = await WavesUser.select_waves_user(
        pgr_uid, ev.user_id, ev.bot_id, game_id=PGR_GAME_ID
    )
    if not pgr_user or not pgr_user.cookie or pgr_user.status == "无效":
        return "战双账号登录已失效，请重新绑定！"

    await WavesUser.update_data_by_uid(
        uid=pgr_uid,
        bot_id=ev.bot_id,
        sign_switch=option,
        bbs_sign_switch=option,
    )

    # 签到结果推送是按用户订阅的, 关闭单个游戏时不退订(可能鸣潮仍开着)
    if ev.bot_id == "onebot" and option != "off":
        await gs_subscribe.add_subscribe("single", BoardcastTypeEnum.SIGN_WAVES, ev)

    act = "开启" if option != "off" else "关闭"
    pref = await get_hide_uid_pref(pgr_uid, ev.user_id, ev.bot_id, game_id=PGR_GAME_ID)
    logger.info(
        f"[库洛签到·配置] user_id={ev.user_id} 战双UID[{pgr_uid}]已[{ev.command[0:2]}]自动签到"
    )

    msg = f"战双 {hide_uid(pgr_uid, user_pref=pref)} 已{act}自动签到"
    if option != "off":
        from .roversign_config import RoverSignConfig

        SIGN_TIME = RoverSignConfig.get_config("SignTime").data
        msg += f"\n😄将于[{SIGN_TIME[0]}:{SIGN_TIME[1]}]点自动为您开始战双签到"
    return msg
