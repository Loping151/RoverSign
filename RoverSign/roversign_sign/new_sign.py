import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.boardcast.models import BoardCastMsg, BoardCastMsgDict

from ..roversign_config.roversign_config import RoverSignConfig
from ..utils.boardcast import send_board_cast_msg
from ..utils.constant import BoardcastTypeEnum
from ..utils.database.models import (
    RoverSign,
    RoverSignData,
    WavesBind,
    WavesUser,
)
from ..utils.database.rover_subscribe import WavesSubscribeReader
from ..utils.database.states import SignStatus
from ..utils.errors import WAVES_CODE_101_MSG
from ..utils.api.api import WAVES_GAME_ID, PGR_GAME_ID
from ..utils.rover_api import rover_api
from ..utils.util import get_hide_uid_pref, hide_uid
from .main import (
    create_sign_info_image,
    do_single_task,
    get_bbs_link_config,
    get_sign_interval,
    pgr_sign_in,
    push_failed_msg,
    sign_in,
    single_daily_sign,
    single_pgr_daily_sign,
    single_task,
)

def get_sign_status():
    """获取签到状态文案"""
    complete_text = RoverSignConfig.get_config("SignCompleteText").data
    incomplete_text = RoverSignConfig.get_config("SignIncompleteText").data
    skip_text = RoverSignConfig.get_config("SignSkipText").data

    return {
        True: complete_text,
        False: incomplete_text,
        "skip": skip_text,
    }


async def get_waves_signin_config():
    """获取鸣潮签到配置"""
    from ..roversign_config.roversign_config import RoverSignConfig

    return RoverSignConfig.get_config("UserWavesSignin").data


async def get_pgr_signin_config():
    """获取战双签到配置"""
    from ..roversign_config.roversign_config import RoverSignConfig

    return RoverSignConfig.get_config("UserPGRSignin").data


async def get_signin_config():
    """向后兼容"""
    return await get_waves_signin_config()


async def get_bbs_signin_config():
    from ..roversign_config.roversign_config import RoverSignConfig

    return RoverSignConfig.get_config("UserBBSSchedSignin").data


async def action_waves_sign_in(uid: str, token: str):
    """鸣潮游戏签到"""
    signed = False
    if not await get_waves_signin_config():
        return signed
    sign_res = await rover_api.sign_in_task_list(uid, token)
    if sign_res.success and sign_res.data and isinstance(sign_res.data, dict):
        signed = sign_res.data.get("isSigIn", False)

    if not signed:
        res = await sign_in(uid, token, isForce=True)
        if "成功" in res or "已签到" in res:
            signed = True

    if signed:
        await RoverSign.upsert_rover_sign(RoverSignData.build_game_sign(uid))

    return signed


async def action_pgr_sign_in(uid: str, token: str):
    """战双游戏签到"""

    signed = False
    if not await get_pgr_signin_config():
        return signed

    # 战双签到需要先获取正确的 serverId，所以直接调用 pgr_sign_in
    # 不在这里检查签到状态（会因为 serverId 不正确而返回 1513 错误）
    res = await pgr_sign_in(uid, token, isForce=False)

    if res is None:
        return "skip"

    if "成功" in res or "已签到" in res:
        signed = True
        logger.info(f"[库洛签到·战双签到] {uid} 签到完成")

    return signed


async def action_sign_in(uid: str, token: str):
    """向后兼容"""
    return await action_waves_sign_in(uid, token)


async def action_bbs_sign_in(uid: str, token: str):
    bbs_signed = False
    if not await get_bbs_signin_config():
        return bbs_signed
    bbs_signed = await do_single_task(uid, token)
    if isinstance(bbs_signed, dict) and all(bbs_signed.values()):
        bbs_signed = True
    elif isinstance(bbs_signed, bool):
        pass
    else:
        bbs_signed = False

    return bbs_signed


async def rover_sign_up_handler(bot: Bot, ev: Event):
    waves_enabled = await get_waves_signin_config()
    pgr_enabled = await get_pgr_signin_config()
    bbs_enabled = await get_bbs_signin_config()

    if not waves_enabled and not pgr_enabled and not bbs_enabled:
        return "签到功能未开启"

    # 获取绑定数据
    bind_data = await WavesBind.select_data(ev.user_id, ev.bot_id)
    if not bind_data:
        return WAVES_CODE_101_MSG

    # 获取所有 UID
    waves_uid_list = []
    if bind_data.uid:
        waves_uid_list = [u for u in bind_data.uid.split("_") if u]

    pgr_uid_list = []
    if bind_data.pgr_uid:
        pgr_uid_list = [u for u in bind_data.pgr_uid.split("_") if u]

    if not waves_uid_list and not pgr_uid_list:
        return WAVES_CODE_101_MSG

    # 国际服鸣潮 UID 走 launcher SDK，KuroBBS 签到接口对它无效，整体跳过
    waves_net_uid_list = [u for u in waves_uid_list if rover_api.is_net(u)]
    waves_uid_list = [u for u in waves_uid_list if not rover_api.is_net(u)]

    # 更新鸣潮账号的最后使用时间
    if waves_uid_list:
        for waves_uid in waves_uid_list:
            await WavesUser.update_last_used_time(
                waves_uid,
                ev.user_id,
                ev.bot_id,
                game_id=WAVES_GAME_ID,
            )

    # 更新战双账号的最后使用时间
    if pgr_uid_list:
        for pgr_uid in pgr_uid_list:
            await WavesUser.update_last_used_time(
                pgr_uid,
                ev.user_id,
                ev.bot_id,
                game_id=PGR_GAME_ID,
            )

    waves_user_prefs = {
        uid: await get_hide_uid_pref(
            uid,
            ev.user_id,
            ev.bot_id,
            game_id=WAVES_GAME_ID,
        )
        for uid in [*waves_uid_list, *waves_net_uid_list]
    }
    pgr_user_prefs = {
        uid: await get_hide_uid_pref(
            uid,
            ev.user_id,
            ev.bot_id,
            game_id=PGR_GAME_ID,
        )
        for uid in pgr_uid_list
    }

    def mask_waves_uid(uid: str) -> str:
        return hide_uid(uid, user_pref=waves_user_prefs.get(uid, ""))

    def mask_pgr_uid(uid: str) -> str:
        return hide_uid(uid, user_pref=pgr_user_prefs.get(uid, ""))

    bbs_link_config = get_bbs_link_config()
    # 社区签到锚点 uid（账号级，任一有效 token 均可）：鸣潮优先，纯战双用户回落到战双 uid
    main_uid = waves_uid_list[0] if waves_uid_list else (pgr_uid_list[0] if pgr_uid_list else None)
    main_game_id = WAVES_GAME_ID if waves_uid_list else PGR_GAME_ID

    # 先检查本地签到状态，判断是否所有签到都已完成
    all_completed = True

    # 检查鸣潮签到状态
    if waves_enabled and waves_uid_list:
        for waves_uid in waves_uid_list:
            rover_sign = await RoverSign.get_sign_data(waves_uid)
            if not rover_sign or not SignStatus.waves_game_sign_complete(rover_sign):
                all_completed = False
                break

    # 检查战双签到状态
    if all_completed and pgr_enabled and pgr_uid_list:
        for pgr_uid in pgr_uid_list:
            rover_sign = await RoverSign.get_sign_data(pgr_uid)
            if not rover_sign or not SignStatus.pgr_game_sign_complete(rover_sign):
                all_completed = False
                break

    # 检查社区签到状态
    if all_completed and bbs_enabled and main_uid:
        rover_sign = await RoverSign.get_sign_data(main_uid)
        if not rover_sign or not SignStatus.bbs_sign_complete(rover_sign, bbs_link_config):
            all_completed = False

    # 如果所有签到都已完成，直接返回跳过消息，不请求任何 API
    if all_completed:
        msg_list = []
        sign_status = get_sign_status()
        if waves_enabled and waves_uid_list:
            for waves_uid in waves_uid_list:
                msg_list.append(f"[鸣潮] 特征码: {mask_waves_uid(waves_uid)}")
                msg_list.append(f"签到状态: {sign_status['skip']}")
                msg_list.append("-----------------------------")

        if pgr_enabled and pgr_uid_list:
            for pgr_uid in pgr_uid_list:
                msg_list.append(f"[战双] 特征码: {mask_pgr_uid(pgr_uid)}")
                msg_list.append(f"签到状态: {sign_status['skip']}")
                msg_list.append("-----------------------------")

        if bbs_enabled and main_uid:
            msg_list.append(f"社区签到状态: {sign_status['skip']}")

        if waves_net_uid_list:
            msg_list.append(
                "国际服 UID 跳过签到(不支持): "
                + ", ".join(mask_waves_uid(u) for u in waves_net_uid_list)
            )

        return "\n".join(msg_list) if msg_list else WAVES_CODE_101_MSG

    # 有未完成的签到，开始获取 token 并执行签到
    msg_list = []
    expire_uid = set()  # 使用 set 自动去重
    main_token = None
    sign_status = get_sign_status()

    if main_uid:
        main_token = await rover_api.get_self_ck(main_uid, ev.user_id, ev.bot_id, game_id=main_game_id)
        if not main_token:
            expire_uid.add(main_uid)

    # 鸣潮签到
    if waves_enabled and waves_uid_list:
        for waves_uid in waves_uid_list:
            token = main_token if waves_uid == main_uid else await rover_api.get_self_waves_ck(waves_uid, ev.user_id, ev.bot_id)
            if not token:
                expire_uid.add(waves_uid)
                continue

            waves_signed = False
            rover_sign: Optional[RoverSign] = await RoverSign.get_sign_data(waves_uid)
            if rover_sign and SignStatus.waves_game_sign_complete(rover_sign):
                waves_signed = "skip"
            else:
                waves_signed = await action_waves_sign_in(waves_uid, token)

            msg_list.append(f"[鸣潮] 特征码: {mask_waves_uid(waves_uid)}")
            msg_list.append(f"签到状态: {sign_status[waves_signed]}")
            msg_list.append("-----------------------------")

            await asyncio.sleep(random.randint(1, 2))

    # 战双签到（用战双账号自己的 token，纯战双用户也能签）
    if pgr_enabled and pgr_uid_list:
        for pgr_uid in pgr_uid_list:
            token = main_token if pgr_uid == main_uid else await rover_api.get_self_ck(
                pgr_uid, ev.user_id, ev.bot_id, game_id=PGR_GAME_ID
            )
            if not token:
                expire_uid.add(pgr_uid)
                continue

            pgr_signed = False
            rover_sign: Optional[RoverSign] = await RoverSign.get_sign_data(pgr_uid)
            if rover_sign and SignStatus.pgr_game_sign_complete(rover_sign):
                pgr_signed = "skip"
            else:
                pgr_signed = await action_pgr_sign_in(pgr_uid, token)

            msg_list.append(f"[战双] 特征码: {mask_pgr_uid(pgr_uid)}")
            msg_list.append(f"签到状态: {sign_status[pgr_signed]}")
            msg_list.append("-----------------------------")

            await asyncio.sleep(random.randint(1, 2))

    # 社区签到（不依赖 UID，只要有 token 就可以）
    if bbs_enabled and main_token:
        bbs_signed = False
        if main_uid:
            rover_sign: Optional[RoverSign] = await RoverSign.get_sign_data(main_uid)
            if rover_sign and SignStatus.bbs_sign_complete(rover_sign, bbs_link_config):
                bbs_signed = "skip"
            else:
                bbs_signed = await action_bbs_sign_in(main_uid, main_token)

        msg_list.append(f"社区签到状态: {sign_status[bbs_signed]}")

    # 失效 UID 提示
    if expire_uid:
        msg_list.append("-----------------------------")
        for uid in expire_uid:
            user_pref = waves_user_prefs.get(uid, pgr_user_prefs.get(uid, ""))
            msg_list.append(f"失效特征码: {hide_uid(uid, user_pref=user_pref)}")

    if waves_net_uid_list:
        msg_list.append(
            "国际服 UID 跳过签到(不支持): "
            + ", ".join(mask_waves_uid(u) for u in waves_net_uid_list)
        )

    return "\n".join(msg_list) if msg_list else WAVES_CODE_101_MSG


# 群/频道类订阅：都按"群发"处理，与旧广播行为(频道也走 group 推送)保持一致
_GROUP_LIKE_TYPES = ("group", "channel", "sub_channel")


def _resolve_report_gid(user: WavesUser, sub_index: Dict):
    """推送去向完全以「开启自动签到时创建的订阅记录」为准。

    返回 (gid, bot_self_id):
      群/频道订阅 -> (group_id, bot_self_id)  走对应群/频道推送
      私聊订阅   -> ("on", None)             走私聊推送
      无订阅     -> ("off", None)            照常签到，但不推送
    """
    sub = sub_index.get((user.user_id, user.bot_id))
    if not sub:
        return "off", None
    user_type, group_id, bot_self_id = sub
    if group_id and user_type in _GROUP_LIKE_TYPES:
        return group_id, (bot_self_id or None)
    if user_type == "direct":
        return "on", None
    return "off", None


async def _load_sign_subscribe_index() -> Dict:
    """预载 SIGN_WAVES 订阅记录：(user_id, bot_id) -> (user_type, group_id, bot_self_id)。

    同一 (user_id, bot_id) 可能有多条(不同 WS 连接)；群/频道订阅优先于私聊，
    避免残留的私聊订阅盖掉群订阅导致本该群发的又走私聊。
    """
    sub_index: Dict = {}
    try:
        subs = await gs_subscribe.get_subscribe(BoardcastTypeEnum.SIGN_WAVES)
        for sub in subs or []:
            key = (sub.user_id, sub.bot_id)
            prev = sub_index.get(key)
            if (
                prev is not None
                and prev[0] in _GROUP_LIKE_TYPES
                and sub.user_type not in _GROUP_LIKE_TYPES
            ):
                continue
            sub_index[key] = (sub.user_type, sub.group_id, sub.bot_self_id)
    except Exception as e:
        logger.warning(f"[库洛签到·推送] 预载签到订阅失败: {e}")
    return sub_index


@dataclass
class _SignJob:
    """同一 cookie 的一组任务：登录一次，每个角色签一次，社区做一次"""

    cookie: str
    game_users: Dict[Tuple[str, int], WavesUser] = field(default_factory=dict)
    bbs_user: Optional[WavesUser] = None


async def rover_auto_sign_task():

    jobs: Dict[str, _SignJob] = {}
    bbs_link_config = get_bbs_link_config()
    _token_dict: Dict[str, list[str]] = {}
    auto_games = RoverSignConfig.get_config("SchedSigninGame").data
    auto_waves = "鸣潮" in auto_games
    auto_pgr = "战双" in auto_games
    sched_game = bool(RoverSignConfig.get_config("SchedSignin").data)
    sched_bbs = bool(RoverSignConfig.get_config("BBSSchedSignin").data)
    master = bool(RoverSignConfig.get_config("SigninMaster").data)

    # 推送去向以订阅记录为准，预载一次
    sub_index = await _load_sign_subscribe_index()

    if sched_bbs or sched_game or master:
        # 获取所有用户（SigninMaster 和定时任务都需要）
        _all_user_list: List[WavesUser] = await WavesUser.get_waves_all_user()

        # 获取活跃用户集合（仅签到活跃账号 / 全部签到跳过不活跃 共用）
        sign_active_only = RoverSignConfig.get_config("SignActiveUserOnly").data
        master_skip_inactive = bool(
            master and RoverSignConfig.get_config("SigninMasterSkipInactive").data
        )
        if sign_active_only or master_skip_inactive:
            active_days = RoverSignConfig.get_config("ActiveUserDays").data
            _active_user_set = set(u.uid for u in await WavesUser.get_active_waves_user(active_days))
            logger.info(f"[库洛签到·签到] 活跃过滤已开启，活跃天数：{active_days}，活跃用户数：{len(_active_user_set)}")
        else:
            _active_user_set = None
            logger.info(f"[库洛签到·签到] 定时任务签到所有账号")

        logger.info(f"[库洛签到·签到] 总用户数：{len(_all_user_list)}")

        sign_map: Dict[str, RoverSign] = {
            r.uid: r for r in await RoverSign.get_all_sign_data_by_date()
        }

        # 社区任务按账号(cookie)算，任一角色下记了完成就算完成
        bbs_done_cookies = set()
        for user in _all_user_list:
            _token_dict.setdefault(user.cookie, []).append(user.uid)
            rover_sign = sign_map.get(user.uid)
            if rover_sign and SignStatus.bbs_sign_complete(rover_sign, bbs_link_config):
                bbs_done_cookies.add(user.cookie)

        def _prefer(prev: Optional[WavesUser], user: WavesUser) -> bool:
            if prev is None:
                return True
            return (prev.user_id, prev.bot_id) not in sub_index and (
                user.user_id,
                user.bot_id,
            ) in sub_index

        for _i, user in enumerate(_all_user_list):
            if _i % 100 == 0:
                await asyncio.sleep(0)

            if not user.user_id or not user.cookie or user.status:
                continue

            # 国际服鸣潮 UID 走 launcher SDK，KuroBBS 签到不支持，跳过
            if user.game_id == WAVES_GAME_ID and rover_api.is_net(user.uid):
                continue

            if master:
                if (
                    master_skip_inactive
                    and _active_user_set is not None
                    and user.uid not in _active_user_set
                ):
                    continue
                want_game = True
                want_bbs = True
            else:
                if _active_user_set is not None and user.uid not in _active_user_set:
                    continue
                want_game = sched_game and user.sign_switch != "off"
                want_bbs = sched_bbs and user.bbs_sign_switch != "off"

            rover_sign = sign_map.get(user.uid)
            if user.game_id == WAVES_GAME_ID:
                want_game = want_game and auto_waves and not (
                    rover_sign and SignStatus.waves_game_sign_complete(rover_sign)
                )
            elif user.game_id == PGR_GAME_ID:
                want_game = want_game and auto_pgr and not (
                    rover_sign and SignStatus.pgr_game_sign_complete(rover_sign)
                )
            else:
                want_game = False
            want_bbs = want_bbs and user.cookie not in bbs_done_cookies

            if not want_game and not want_bbs:
                continue

            job = jobs.setdefault(user.cookie, _SignJob(user.cookie))
            if want_game:
                key = (user.uid, user.game_id)
                if _prefer(job.game_users.get(key), user):
                    job.game_users[key] = user
            if want_bbs and _prefer(job.bbs_user, user):
                job.bbs_user = user

    private_waves_sign_msgs = {}
    group_waves_sign_msgs = {}
    all_waves_sign_msgs = {"failed": 0, "success": 0}

    private_pgr_sign_msgs = {}
    group_pgr_sign_msgs = {}
    all_pgr_sign_msgs = {"failed": 0, "success": 0}

    private_bbs_msgs = {}
    group_bbs_msgs = {}
    all_bbs_msgs = {"failed": 0, "success": 0}

    _USER_TIMEOUT = 120  # 单个角色签到超时（秒）

    def _report_request_failed(user: WavesUser, res, is_game: bool):
        if res.is_token_invalid or res.is_bat_token_invalid:
            return
        gid, bot_self = _resolve_report_gid(user, sub_index)
        im = f"签到失败：{res.throw_msg()}"
        if not is_game:
            targets = (private_bbs_msgs, group_bbs_msgs, all_bbs_msgs)
        elif user.game_id == PGR_GAME_ID:
            targets = (private_pgr_sign_msgs, group_pgr_sign_msgs, all_pgr_sign_msgs)
            im = f"[战双] {im}"
        else:
            targets = (private_waves_sign_msgs, group_waves_sign_msgs, all_waves_sign_msgs)
        push_failed_msg(user.bot_id, user.uid, gid, user.user_id, im, *targets, bot_self)

    async def _process_job_inner(job: _SignJob):
        await asyncio.sleep(random.random() * 1.5)

        game_users = list(job.game_users.values())
        first = game_users[0] if game_users else job.bbs_user
        if first is None:
            return

        async with rover_api.session_scope():
            login_res = await rover_api.login_log(first.uid, job.cookie, game_id=first.game_id)
            if not login_res.success:
                if login_res.is_bat_token_invalid:
                    await rover_api.refresh_bat_token(first)
                else:
                    for user in game_users:
                        await login_res.mark_cookie_invalid(user.uid, job.cookie)
                        _report_request_failed(user, login_res, True)
                    if job.bbs_user and all(job.bbs_user is not u for u in game_users):
                        await login_res.mark_cookie_invalid(job.bbs_user.uid, job.cookie)
                        _report_request_failed(job.bbs_user, login_res, False)
                return

            for user in game_users:
                report_gid, report_bot_self = _resolve_report_gid(user, sub_index)
                rover_sign = await RoverSign.get_sign_data(user.uid)

                if user.game_id == PGR_GAME_ID:
                    if rover_sign and SignStatus.pgr_game_sign_complete(rover_sign):
                        continue
                    await asyncio.sleep(random.randint(1, 2))
                    logger.info(f"[库洛签到·战双签到] 开始为 UID {user.uid} 执行战双签到")
                    await single_pgr_daily_sign(
                        user.bot_id,
                        user.uid,
                        report_gid,
                        user.user_id,
                        job.cookie,
                        private_pgr_sign_msgs,
                        group_pgr_sign_msgs,
                        all_pgr_sign_msgs,
                        report_bot_self,
                    )
                else:
                    if rover_sign and SignStatus.waves_game_sign_complete(rover_sign):
                        continue
                    refresh_res = await rover_api.refresh_data(
                        user.uid, job.cookie, game_id=user.game_id
                    )
                    if not refresh_res.success:
                        if refresh_res.is_bat_token_invalid:
                            await rover_api.refresh_bat_token(user)
                        else:
                            await refresh_res.mark_cookie_invalid(user.uid, job.cookie)
                            _report_request_failed(user, refresh_res, True)
                        continue
                    await asyncio.sleep(random.randint(1, 2))
                    await single_daily_sign(
                        user.bot_id,
                        user.uid,
                        report_gid,
                        user.user_id,
                        job.cookie,
                        private_waves_sign_msgs,
                        group_waves_sign_msgs,
                        all_waves_sign_msgs,
                        report_bot_self,
                    )

                await asyncio.sleep(random.random() * 2)

            user = job.bbs_user
            if user:
                rover_signs = [await RoverSign.get_sign_data(uid) for uid in _token_dict.get(job.cookie, [])]
                if any(r and SignStatus.bbs_sign_complete(r, bbs_link_config) for r in rover_signs):
                    logger.debug(f"[库洛签到·社区] UID {user.uid} 今日已完成，跳过")
                else:
                    report_gid, report_bot_self = _resolve_report_gid(user, sub_index)
                    await single_task(
                        user.bot_id,
                        user.uid,
                        report_gid,
                        user.user_id,
                        job.cookie,
                        private_bbs_msgs,
                        group_bbs_msgs,
                        all_bbs_msgs,
                        report_bot_self,
                    )
                    await asyncio.sleep(random.randint(2, 4))
        logger.info(f"[库洛签到·自动] UID {first.uid} 签到任务完成")

    async def process_job(semaphore, job: _SignJob):
        timeout = _USER_TIMEOUT * max(1, len(job.game_users))
        async with semaphore:
            try:
                await asyncio.wait_for(_process_job_inner(job), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"[库洛签到·自动] 账号签到超时（{timeout}s），跳过")
            except Exception as e:
                logger.error(f"[库洛签到·自动] 账号签到异常: {e}")

    if not jobs:
        return "暂无需要签到的账号"

    logger.info(
        f"[库洛签到·签到] 本轮待处理账号：{len(jobs)}，"
        f"游戏签到：{sum(len(j.game_users) for j in jobs.values())}，"
        f"社区任务：{sum(1 for j in jobs.values() if j.bbs_user)}"
    )

    max_concurrent: int = RoverSignConfig.get_config("SigninConcurrentNum").data
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [process_job(semaphore, job) for job in jobs.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            return f"{result.args[0]}"

    # 合并鸣潮和战双的签到消息
    combined_private_sign_msgs = {}
    combined_group_sign_msgs = {}

    # 合并私聊消息
    for qid, msgs in private_waves_sign_msgs.items():
        combined_private_sign_msgs[qid] = msgs

    for qid, msgs in private_pgr_sign_msgs.items():
        if qid in combined_private_sign_msgs:
            combined_private_sign_msgs[qid].extend(msgs)
        else:
            combined_private_sign_msgs[qid] = msgs

    # 合并群消息
    for gid, data in group_waves_sign_msgs.items():
        combined_group_sign_msgs[gid] = data.copy()

    for gid, data in group_pgr_sign_msgs.items():
        if gid in combined_group_sign_msgs:
            combined_group_sign_msgs[gid]["success"] += data["success"]
            combined_group_sign_msgs[gid]["failed"] += data["failed"]
            combined_group_sign_msgs[gid]["push_message"].extend(data["push_message"])
            if not combined_group_sign_msgs[gid].get("bot_self_id") and data.get(
                "bot_self_id"
            ):
                combined_group_sign_msgs[gid]["bot_self_id"] = data["bot_self_id"]
        else:
            combined_group_sign_msgs[gid] = data.copy()

    # 游戏签到结果广播（包含鸣潮和战双）
    game_sign_result = await to_board_cast_msg(
        combined_private_sign_msgs, combined_group_sign_msgs, "游戏签到", theme="blue"
    )
    if not RoverSignConfig.get_config("PrivateSignReport").data:
        game_sign_result["private_msg_dict"] = {}
    if not RoverSignConfig.get_config("GroupSignReport").data:
        game_sign_result["group_msg_dict"] = {}
    await send_board_cast_msg(game_sign_result, BoardcastTypeEnum.SIGN_WAVES)

    # 社区签到结果广播
    bbs_result = await to_board_cast_msg(
        private_bbs_msgs, group_bbs_msgs, "社区签到", theme="yellow"
    )
    if not RoverSignConfig.get_config("PrivateSignReport").data:
        bbs_result["private_msg_dict"] = {}
    if not RoverSignConfig.get_config("GroupSignReport").data:
        bbs_result["group_msg_dict"] = {}
    await send_board_cast_msg(bbs_result, BoardcastTypeEnum.SIGN_WAVES)

    # 构建返回消息
    msg_parts = ["[库洛]自动任务"]

    if all_waves_sign_msgs['success'] > 0:
        msg_parts.append(f"今日成功鸣潮签到 {all_waves_sign_msgs['success']} 个账号")

    if all_pgr_sign_msgs['success'] > 0:
        msg_parts.append(f"今日成功战双签到 {all_pgr_sign_msgs['success']} 个账号")

    if all_bbs_msgs['success'] > 0:
        msg_parts.append(f"今日社区签到 {all_bbs_msgs['success']} 个账号")

    return "\n".join(msg_parts)


async def to_board_cast_msg(
    private_msgs,
    group_msgs,
    type: Literal["社区签到", "游戏签到"] = "社区签到",
    theme: str = "yellow",
):
    # 转为广播消息
    private_msg_dict: Dict[str, List[BoardCastMsg]] = {}
    group_msg_dict: Dict[str, BoardCastMsg] = {}
    for qid in private_msgs:
        msgs = []
        for _, i in enumerate(private_msgs[qid]):
            if _ > 0:
                msgs.append(MessageSegment.text("\n"))
            msgs.extend(i["msg"])

        if qid not in private_msg_dict:
            private_msg_dict[qid] = []

        private_msg_dict[qid].append(
            {
                "bot_id": private_msgs[qid][0]["bot_id"],
                "messages": msgs,
            }
        )

    failed_num = 0
    success_num = 0
    for gid in group_msgs:
        success = group_msgs[gid]["success"]
        faild = group_msgs[gid]["failed"]
        success_num += int(success)
        failed_num += int(faild)
        title = f"✅[鸣潮]今日{type}任务已完成！\n本群共签到成功{success}人\n共签到失败{faild}人"
        messages = []
        if RoverSignConfig.get_config("GroupSignReportPic").data:
            image = create_sign_info_image(title, theme="yellow")
            messages.append(MessageSegment.image(image))
        else:
            messages.append(MessageSegment.text(title))
        if group_msgs[gid]["push_message"]:
            messages.append(MessageSegment.text("\n"))
            messages.extend(group_msgs[gid]["push_message"])

        # bot_id 是平台 ID；bot_self_id 是机器人自身账号，二者不能混用。
        # 优先用订阅记录里带过来的 bot_self_id，其次近期记录，兜底兼容旧订阅数据。
        from ..utils.database.rover_subscribe import RoverSubscribe
        bot_self_id = group_msgs[gid].get("bot_self_id") or ""
        if not bot_self_id:
            bot_self_id = await RoverSubscribe.get_group_bot(gid)
        if not bot_self_id:
            bot_self_id = await WavesSubscribeReader.get_group_bot(gid)
        if not bot_self_id:
            legacy_bot_id = str(group_msgs[gid].get("bot_id", ""))
            if legacy_bot_id.isdigit():
                bot_self_id = legacy_bot_id
                logger.debug(
                    f"[库洛签到·签到] 群 {gid} 未找到 bot_self_id，"
                    f"使用旧广播结构中的数字 bot_id 兜底: {bot_self_id}"
                )
            else:
                logger.warning(f"[库洛签到·签到] 群 {gid} 未找到 bot_self_id，跳过群推送组装")
                continue

        group_msg_dict[gid] = {
            "bot_id": group_msgs[gid]["bot_id"],
            "bot_self_id": bot_self_id,
            "messages": messages,
        }

    result: BoardCastMsgDict = {
        "private_msg_dict": private_msg_dict,
        "group_msg_dict": group_msg_dict,
    }
    return result
