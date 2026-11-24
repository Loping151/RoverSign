from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix

from ..utils.api.api import PGR_GAME_ID, WAVES_GAME_ID
from ..utils.database.models import WavesBind
from ..utils.util import get_hide_uid_pref, hide_uid
from .set_config import get_signin_config, set_config_func, set_pgr_config_func

sv_rover_config = SV("RoverSign配置")


PREFIX = get_plugin_available_prefix("RoverSign")


@sv_rover_config.on_prefix(
    ("开启", "关闭"),
    to_ai="""开启或关闭自己鸣潮 / 战双账号的每日自动签到任务。

当用户问「开启自动签到 / 开启鸣潮自动签到 / 开启战双自动签到 / 关闭…」时调用。
text 取 "自动签到"（鸣潮、战双名下全部账号）/ "鸣潮自动签到"（仅鸣潮当前 uid）/ "战双自动签到"（仅战双当前 uid）。
需绑定 cookie。命令字本身（"开启" / "关闭"）决定开还是关。

Args:
    text: "自动签到" / "鸣潮自动签到" / "战双自动签到"。例: command="开启" + text="自动签到"。
""",
)
async def open_switch_func(bot: Bot, ev: Event):
    if ev.text == "战双自动签到":
        return await _handle_pgr_switch(bot, ev)
    if ev.text == "自动签到":
        return await _handle_all_switch(bot, ev)
    if ev.text != "鸣潮自动签到":
        return

    at_sender = True if ev.group_id else False
    uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
    if uid is None:
        msg = f"您还未绑定鸣潮特征码, 请使用【{PREFIX}绑定uid】完成绑定！"
        return await bot.send(
            (" " if at_sender else "") + msg,
            at_sender,
        )

    from ..utils.rover_api import rover_api

    token = await rover_api.get_self_waves_ck(uid, ev.user_id, ev.bot_id)
    if not token:
        from ..utils.errors import WAVES_CODE_101_MSG

        user_pref = await get_hide_uid_pref(
            uid,
            ev.user_id,
            ev.bot_id,
            game_id=WAVES_GAME_ID,
        )
        msg = (
            f"当前特征码：{hide_uid(uid, user_pref=user_pref)}\n"
            f"{WAVES_CODE_101_MSG.rstrip(chr(10))}"
        )
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    logger.info(f"[库洛签到·配置] user_id={ev.user_id} 尝试[{ev.command[0:2]}]了[{ev.text}]功能")

    im = await set_config_func(ev, uid)
    im = im.rstrip("\n") if isinstance(im, str) else im
    await bot.send((" " if at_sender and isinstance(im, str) else "") + im if isinstance(im, str) else im, at_sender)


async def _handle_all_switch(bot: Bot, ev: Event):
    """不指定游戏: 鸣潮、战双名下全部账号一起开关"""
    from ..utils.rover_api import rover_api
    from .roversign_config import RoverSignConfig

    at_sender = True if ev.group_id else False
    if not await get_signin_config():
        return await bot.send((" " if at_sender else "") + "自动签到功能已禁用!", at_sender)

    waves_uids = [
        u for u in await WavesBind.get_uid_list_by_game(ev.user_id, ev.bot_id) or [] if not rover_api.is_net(u)
    ]
    pgr_uids = await WavesBind.get_uid_list_by_game(ev.user_id, ev.bot_id, game_name="pgr") or []
    if not waves_uids and not pgr_uids:
        msg = f"您还未绑定特征码, 请使用【{PREFIX}绑定uid】完成绑定！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    act = "开启" if "开启" in ev.command else "关闭"
    lines: list[str] = []
    done = False
    for uid in waves_uids:
        pref = await get_hide_uid_pref(uid, ev.user_id, ev.bot_id, game_id=WAVES_GAME_ID)
        name = f"鸣潮 {hide_uid(uid, user_pref=pref)}"
        if not await rover_api.get_self_waves_ck(uid, ev.user_id, ev.bot_id):
            lines.append(f"{name} 登录已失效，请重新登录")
            continue
        ev.text = "鸣潮自动签到"
        await set_config_func(ev, uid)
        lines.append(f"{name} 已{act}自动签到")
        done = True
    for pgr_uid in pgr_uids:
        ev.text = "战双自动签到"
        first = (await set_pgr_config_func(ev, pgr_uid)).split("\n")[0]
        if not first.startswith("战双 "):
            pref = await get_hide_uid_pref(pgr_uid, ev.user_id, ev.bot_id, game_id=PGR_GAME_ID)
            first = f"战双 {hide_uid(pgr_uid, user_pref=pref)} {first.removeprefix('战双').rstrip('!！')}"
        lines.append(first)
        done = done or f"已{act}" in first
    ev.text = "自动签到"
    logger.info(f"[库洛签到·配置] user_id={ev.user_id} [{act}]全部自动签到: 鸣潮{waves_uids} 战双{pgr_uids}")

    if done and act == "开启":
        sign_time = RoverSignConfig.get_config("SignTime").data
        lines.append(f"😄将于[{sign_time[0]}:{sign_time[1]}]点自动为您签到")
    await bot.send((" " if at_sender else "") + "\n".join(lines), at_sender)


async def _handle_pgr_switch(bot: Bot, ev: Event):
    at_sender = True if ev.group_id else False
    pgr_uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id, game_name="pgr")
    if pgr_uid is None:
        msg = "您还未绑定战双特征码！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    logger.info(f"[库洛签到·配置] user_id={ev.user_id} 尝试[{ev.command[0:2]}]了[{ev.text}]功能")

    im = await set_pgr_config_func(ev, pgr_uid)
    im = im.rstrip("\n") if isinstance(im, str) else im
    await bot.send((" " if at_sender and isinstance(im, str) else "") + im if isinstance(im, str) else im, at_sender)


@sv_rover_config.on_fullmatch(
    ("自动签到", "鸣潮自动签到", "开始自动签到", "打开自动签到", "鸣潮开启自动签到", "自动化签到", "开启自动化签到"),
    block=True,
)
async def open_auto_sign_alias(bot: Bot, ev: Event):
    ev.text = "鸣潮自动签到" if ev.command.startswith("鸣潮") else "自动签到"
    ev.command = "开启"
    return await open_switch_func(bot, ev)
