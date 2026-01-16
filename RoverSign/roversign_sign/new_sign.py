import asyncio
import random
from typing import Dict, List, Literal, Optional

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
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
from ..utils.database.states import SignStatus
from ..utils.errors import WAVES_CODE_101_MSG
from ..utils.api.api import WAVES_GAME_ID, PGR_GAME_ID
from ..utils.rover_api import rover_api
from .main import (
    create_sign_info_image,
    do_single_task,
    get_bbs_link_config,
    get_sign_interval,
    pgr_sign_in,
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
        logger.info(f"[战双签到] {uid} 签到完成")

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

    bbs_link_config = get_bbs_link_config()
    main_uid = waves_uid_list[0] if waves_uid_list else None

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
                msg_list.append(f"[鸣潮] 特征码: {waves_uid}")
                msg_list.append(f"签到状态: {sign_status['skip']}")
                msg_list.append("-----------------------------")

        if pgr_enabled and pgr_uid_list:
            for pgr_uid in pgr_uid_list:
                msg_list.append(f"[战双] 特征码: {pgr_uid}")
                msg_list.append(f"签到状态: {sign_status['skip']}")
                msg_list.append("-----------------------------")

        if bbs_enabled and main_uid:
            msg_list.append(f"社区签到状态: {sign_status['skip']}")

        return "\n".join(msg_list) if msg_list else WAVES_CODE_101_MSG

    # 有未完成的签到，开始获取 token 并执行签到
    msg_list = []
    expire_uid = set()  # 使用 set 自动去重
    main_token = None
    sign_status = get_sign_status()

    if main_uid:
        main_token = await rover_api.get_self_waves_ck(main_uid, ev.user_id, ev.bot_id)
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

            msg_list.append(f"[鸣潮] 特征码: {waves_uid}")
            msg_list.append(f"签到状态: {sign_status[waves_signed]}")
            msg_list.append("-----------------------------")

            await asyncio.sleep(random.randint(1, 2))

    # 战双签到
    if pgr_enabled and pgr_uid_list and main_token:
        for pgr_uid in pgr_uid_list:
            pgr_signed = False
            rover_sign: Optional[RoverSign] = await RoverSign.get_sign_data(pgr_uid)
            if rover_sign and SignStatus.pgr_game_sign_complete(rover_sign):
                pgr_signed = "skip"
            else:
                pgr_signed = await action_pgr_sign_in(pgr_uid, main_token)

            msg_list.append(f"[战双] 特征码: {pgr_uid}")
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
            msg_list.append(f"失效特征码: {uid}")

    return "\n".join(msg_list) if msg_list else WAVES_CODE_101_MSG


async def rover_auto_sign_task():

    need_user_list: List[WavesUser] = []
    bbs_user = set()
    waves_sign_user = set()
    pgr_sign_user = set()
    bbs_link_config = get_bbs_link_config()
    _token_dict: Dict[str, list[str]] = {}
    if (
        RoverSignConfig.get_config("BBSSchedSignin").data
        or RoverSignConfig.get_config("SchedSignin").data
        or RoverSignConfig.get_config("UserPGRSignin").data
    ):
        # 获取所有用户（SigninMaster 和定时任务都需要）
        _all_user_list: List[WavesUser] = await WavesUser.get_waves_all_user()

        # 获取活跃用户（仅用于定时任务）
        sign_active_only = RoverSignConfig.get_config("SignActiveUserOnly").data
        if sign_active_only:
            active_days = RoverSignConfig.get_config("ActiveUserDays").data
            _active_user_set = set(u.uid for u in await WavesUser.get_active_waves_user(active_days))
            logger.info(f"[RoverSign] 定时任务仅签到活跃账号，活跃天数：{active_days}，活跃用户数：{len(_active_user_set)}")
        else:
            _active_user_set = None
            logger.info(f"[RoverSign] 定时任务签到所有账号")

        logger.info(f"[RoverSign] 总用户数：{len(_all_user_list)}")

        for user in _all_user_list:
            _uid = user.user_id
            if not _uid:
                continue

            is_signed_waves_game = False
            is_signed_pgr_game = False
            is_signed_bbs = False
            rover_sign: Optional[RoverSign] = await RoverSign.get_sign_data(user.uid)
            if rover_sign:
                if SignStatus.waves_game_sign_complete(rover_sign):
                    is_signed_waves_game = True
                if SignStatus.pgr_game_sign_complete(rover_sign):
                    is_signed_pgr_game = True
                if SignStatus.bbs_sign_complete(rover_sign, bbs_link_config):
                    is_signed_bbs = True

            _token_dict.setdefault(user.cookie, []).append(user.uid)
            if user.game_id == WAVES_GAME_ID:
                if is_signed_waves_game and is_signed_bbs:
                    continue
            elif user.game_id == PGR_GAME_ID:
                if is_signed_pgr_game and is_signed_bbs:
                    continue
            elif is_signed_bbs:
                continue

            if RoverSignConfig.get_config("SigninMaster").data:
                # 如果 SigninMaster 为 True，不判断活跃，直接添加到 user_list 中
                need_user_list.append(user)
                if not is_signed_bbs:
                    bbs_user.add(user.uid)
                # 根据 game_id 判断加入哪个游戏签到列表
                if user.game_id == WAVES_GAME_ID and not is_signed_waves_game:
                    waves_sign_user.add(user.uid)
                elif user.game_id == PGR_GAME_ID and not is_signed_pgr_game:
                    pgr_sign_user.add(user.uid)
                continue

            # 定时任务：判断是否开启了活跃过滤
            if _active_user_set is not None and user.uid not in _active_user_set:
                # 开启了活跃过滤，且该用户不活跃，跳过
                continue

            is_need = False
            if user.bbs_sign_switch != "off":
                # 如果 bbs_sign_switch 不为 'off'，添加到 user_list 中
                bbs_user.add(user.uid)
                is_need = True

            if user.sign_switch != "off":
                # 如果 sign_switch 不为 'off'，根据 game_id 判断加入哪个游戏签到列表
                if user.game_id == WAVES_GAME_ID:
                    waves_sign_user.add(user.uid)
                elif user.game_id == PGR_GAME_ID:
                    pgr_sign_user.add(user.uid)
                is_need = True

            if is_need:
                need_user_list.append(user)

    private_waves_sign_msgs = {}
    group_waves_sign_msgs = {}
    all_waves_sign_msgs = {"failed": 0, "success": 0}

    private_pgr_sign_msgs = {}
    group_pgr_sign_msgs = {}
    all_pgr_sign_msgs = {"failed": 0, "success": 0}

    private_bbs_msgs = {}
    group_bbs_msgs = {}
    all_bbs_msgs = {"failed": 0, "success": 0}

    async def process_user(semaphore, user: WavesUser):
        logger.debug(f"[自动签到] 处理 UID {user.uid} 的签到任务")
        async with semaphore:
            await asyncio.sleep(random.random() * 1.5)
            if user.cookie == "":
                return
            if user.status:
                return

            user_game_id = user.game_id

            login_res = await rover_api.login_log(user.uid, user.cookie, game_id=user_game_id)
            if not login_res.success:
                if login_res.is_bat_token_invalid:
                    if waves_user := await rover_api.refresh_bat_token(user):
                        user.cookie = waves_user.cookie
                else:
                    await login_res.mark_cookie_invalid(user.uid, user.cookie)
                return

            refresh_res = await rover_api.refresh_data(user.uid, user.cookie, game_id=user_game_id)
            if not refresh_res.success:
                if refresh_res.is_bat_token_invalid:
                    if waves_user := await rover_api.refresh_bat_token(user):
                        user.cookie = waves_user.cookie
                else:
                    await refresh_res.mark_cookie_invalid(user.uid, user.cookie)
                return

            await asyncio.sleep(random.randint(1, 2))
            
            # 战双签到
            if (
                RoverSignConfig.get_config("SchedSignin").data and user.uid in pgr_sign_user
            ) or RoverSignConfig.get_config("SigninMaster").data and user.uid in pgr_sign_user:
                logger.info(f"[战双签到] 开始为 UID {user.uid} 执行战双签到")
                await single_pgr_daily_sign(
                    user.bot_id,
                    user.uid,
                    user.sign_switch,
                    user.user_id,
                    user.cookie,
                    private_pgr_sign_msgs,
                    group_pgr_sign_msgs,
                    all_pgr_sign_msgs,
                )

                await asyncio.sleep(random.random() * 2)

            # 鸣潮签到
            if (
                RoverSignConfig.get_config("SchedSignin").data and user.uid in waves_sign_user
            ) or RoverSignConfig.get_config("SigninMaster").data and user.uid in waves_sign_user:
                await single_daily_sign(
                    user.bot_id,
                    user.uid,
                    user.sign_switch,
                    user.user_id,
                    user.cookie,
                    private_waves_sign_msgs,
                    group_waves_sign_msgs,
                    all_waves_sign_msgs,
                )

                await asyncio.sleep(random.random() * 2)
                
            # 社区签到
            if (
                RoverSignConfig.get_config("BBSSchedSignin").data
                and user.uid in bbs_user
            ) or RoverSignConfig.get_config("SigninMaster").data:
                # 先检查本地签到状态，避免重复请求 API
                rover_sign = [await RoverSign.get_sign_data(uid) for uid in _token_dict.get(user.cookie, [])]
                if any([rover and SignStatus.bbs_sign_complete(rover, bbs_link_config) for rover in rover_sign]):
                    # 已完成社区签到，跳过
                    logger.debug(f"[社区签到] UID {user.uid} 今日已完成，跳过")
                else:
                    await single_task(
                        user.bot_id,
                        user.uid,
                        user.bbs_sign_switch,
                        user.user_id,
                        user.cookie,
                        private_bbs_msgs,
                        group_bbs_msgs,
                        all_bbs_msgs,
                    )

                await asyncio.sleep(random.randint(2, 4))
            logger.info(f"[自动签到] UID {user.uid} 签到任务完成")

    if not need_user_list:
        return "暂无需要签到的账号"

    max_concurrent: int = RoverSignConfig.get_config("SigninConcurrentNum").data
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [process_user(semaphore, user) for user in need_user_list]
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
        for i in private_msgs[qid]:
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
        group_msg_dict[gid] = {
            "bot_id": group_msgs[gid]["bot_id"],
            "messages": messages,
        }

    result: BoardCastMsgDict = {
        "private_msg_dict": private_msg_dict,
        "group_msg_dict": group_msg_dict,
    }
    return result
