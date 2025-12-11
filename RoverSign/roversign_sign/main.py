import asyncio
import random
from typing import Dict, Optional, Set, Union

from PIL import Image, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

from ..roversign_config.roversign_config import RoverSignConfig
from ..utils.database.models import RoverSign, RoverSignData
from ..utils.database.states import SignStatus
from ..utils.fonts.waves_fonts import waves_font_24
from ..utils.rover_api import rover_api

BBS_TASK_KEYWORDS: Dict[str, str] = {
    "bbs_sign": "签到",
    "bbs_detail": "浏览",
    "bbs_like": "点赞",
    "bbs_share": "分享",
}

BBS_TASK_LABELS: Dict[str, str] = {
    "bbs_sign": "用户签到",
    "bbs_detail": "浏览帖子",
    "bbs_like": "点赞帖子",
    "bbs_share": "分享帖子",
}


def get_bbs_link_config() -> Set[str]:
    bbs_link = RoverSignConfig.get_config("BBSLink").data
    return set(bbs_link) if bbs_link else set()


def get_task_key_from_remark(remark: Optional[str]) -> Optional[str]:
    if not remark:
        return None
    for key, keyword in BBS_TASK_KEYWORDS.items():
        if keyword in remark:
            return key
    return None


async def get_sign_interval(is_bbs: bool = False):
    next_group_sign_time = RoverSignConfig.get_config(
        "SigninConcurrentNumInterval"
    ).data
    ratio = random.uniform(1, 2) if is_bbs else 1
    if not next_group_sign_time:
        return random.uniform(2, 3) * ratio
    return (
        random.uniform(float(next_group_sign_time[0]), float(next_group_sign_time[1]))
        * ratio
    )


async def do_sign_in(taskData, uid, token, rover_sign: RoverSignData):
    if (
        taskData["completeTimes"] == taskData["needActionTimes"]
        or rover_sign.bbs_sign == SignStatus.BBS_SIGN
    ):
        rover_sign.bbs_sign = SignStatus.BBS_SIGN
        return True

    # 用户签到
    sign_in_res = await rover_api.do_sign_in(uid, token)
    if not sign_in_res or not sign_in_res.success:
        return False
    if sign_in_res.code == 200:
        # 签到成功
        rover_sign.bbs_sign = SignStatus.BBS_SIGN
        return True
    logger.warning(f"[鸣潮][社区签到]签到失败 uid: {uid} sign_in_res: {sign_in_res}")
    return False


async def do_detail(
    taskData,
    uid,
    token,
    post_list,
    rover_sign: RoverSignData,
):
    if (
        taskData["completeTimes"] == taskData["needActionTimes"]
        or rover_sign.bbs_detail == SignStatus.BBS_DETAIL
    ):
        rover_sign.bbs_detail = SignStatus.BBS_DETAIL
        return True
    # 浏览帖子
    detail_succ = 0
    for i, post in enumerate(post_list):
        post_detail_res = await rover_api.do_post_detail(uid, token, post["postId"])
        if not post_detail_res or not post_detail_res.success:
            break
        if post_detail_res.code == 200:
            detail_succ += 1
            # 浏览成功
            rover_sign.bbs_detail = (
                rover_sign.bbs_detail + 1 if rover_sign.bbs_detail else 1
            )
        else:
            # 浏览失败
            break
        if detail_succ >= taskData["needActionTimes"] - taskData["completeTimes"]:
            rover_sign.bbs_detail = SignStatus.BBS_DETAIL
            return True

        await asyncio.sleep(random.uniform(0, 1))

    logger.warning(f"[鸣潮][社区签到]浏览失败 uid: {uid}")
    return False


async def do_like(
    taskData,
    uid,
    token,
    post_list,
    rover_sign: RoverSignData,
):
    if (
        taskData["completeTimes"] == taskData["needActionTimes"]
        or rover_sign.bbs_like == SignStatus.BBS_LIKE
    ):
        rover_sign.bbs_like = SignStatus.BBS_LIKE
        return True

    # 用户点赞5次
    like_succ = 0
    for i, post in enumerate(post_list):
        like_res = await rover_api.do_like(uid, token, post["postId"], post["userId"])
        if not like_res or not like_res.success:
            break
        if like_res.code == 200:
            like_succ += 1
            # 点赞成功
            rover_sign.bbs_like = rover_sign.bbs_like + 1 if rover_sign.bbs_like else 1
        else:
            # 点赞失败
            break
        if like_succ >= taskData["needActionTimes"] - taskData["completeTimes"]:
            rover_sign.bbs_like = SignStatus.BBS_LIKE
            return True

        await asyncio.sleep(random.uniform(0, 1))

    logger.warning(f"[鸣潮][社区签到]点赞失败 uid: {uid}")
    return False


async def do_share(
    taskData,
    uid,
    token,
    rover_sign: RoverSignData,
):
    if (
        taskData["completeTimes"] == taskData["needActionTimes"]
        or rover_sign.bbs_share == SignStatus.BBS_SHARE
    ):
        rover_sign.bbs_share = SignStatus.BBS_SHARE
        return True

    # 分享
    share_res = await rover_api.do_share(uid, token)
    if not share_res or not share_res.success:
        return False
    if share_res.code == 200:
        # 分享成功
        rover_sign.bbs_share = SignStatus.BBS_SHARE
        return True

    logger.exception(f"[鸣潮][社区签到]分享失败 uid: {uid}")
    return False


async def do_single_task(uid, token) -> Union[bool, Dict[str, bool]]:
    rover_sign = await RoverSign.get_sign_data(uid)
    if not rover_sign:
        rover_sign = RoverSignData.build_bbs_sign(uid)

    bbs_link_config = get_bbs_link_config()
    if not bbs_link_config:
        return True

    # 任务列表
    task_res = await rover_api.get_task(token, uid)
    if not task_res or not task_res.success:
        return False
    if not task_res.data or not isinstance(task_res.data, dict):
        return False

    daily_tasks = task_res.data.get("dailyTask") or []
    filtered_tasks = []
    for task in daily_tasks:
        task_key = get_task_key_from_remark(task.get("remark"))
        if task_key and task_key in bbs_link_config:
            filtered_tasks.append((task_key, task))

    if not filtered_tasks:
        return True

    if all(
        task["completeTimes"] == task["needActionTimes"] for _, task in filtered_tasks
    ):
        is_save = False
        if "bbs_sign" in bbs_link_config and rover_sign.bbs_sign != SignStatus.BBS_SIGN:
            rover_sign.bbs_sign = SignStatus.BBS_SIGN
            is_save = True
        if (
            "bbs_detail" in bbs_link_config
            and rover_sign.bbs_detail != SignStatus.BBS_DETAIL
        ):
            rover_sign.bbs_detail = SignStatus.BBS_DETAIL
            is_save = True
        if "bbs_like" in bbs_link_config and rover_sign.bbs_like != SignStatus.BBS_LIKE:
            rover_sign.bbs_like = SignStatus.BBS_LIKE
            is_save = True
        if (
            "bbs_share" in bbs_link_config
            and rover_sign.bbs_share != SignStatus.BBS_SHARE
        ):
            rover_sign.bbs_share = SignStatus.BBS_SHARE
            is_save = True
        if is_save:
            await RoverSign.upsert_rover_sign(rover_sign)
        return True

    # check 1
    need_post_list_flag = any(
        task_key in {"bbs_detail", "bbs_like"}
        and task["completeTimes"] != task["needActionTimes"]
        for task_key, task in filtered_tasks
    )

    post_list = []
    if need_post_list_flag:
        # 获取帖子
        form_list_res = await rover_api.get_form_list(token)
        if not form_list_res or not form_list_res.success:
            return False
        if form_list_res.data and isinstance(form_list_res.data, dict):
            # 获取到帖子列表
            post_list = form_list_res.data["postList"]
            random.shuffle(post_list)
        if not post_list:
            logger.exception(
                f"[鸣潮][社区签到]获取帖子列表失败 uid: {uid} res: {form_list_res}"
            )
            # 未获取帖子列表
            return False

    form_result = {
        BBS_TASK_LABELS[task_key]: False
        for task_key in bbs_link_config
        if task_key in BBS_TASK_LABELS
    }

    # 随机打乱任务列表
    random.shuffle(filtered_tasks)

    # 获取到任务列表
    for task_key, task in filtered_tasks:
        label = BBS_TASK_LABELS.get(task_key)
        if not label:
            continue
        if task_key == "bbs_sign":
            form_result[label] = await do_sign_in(task, uid, token, rover_sign)
        elif task_key == "bbs_detail":
            form_result[label] = await do_detail(
                task, uid, token, post_list, rover_sign
            )
        elif task_key == "bbs_like":
            form_result[label] = await do_like(task, uid, token, post_list, rover_sign)
        elif task_key == "bbs_share":
            form_result[label] = await do_share(task, uid, token, rover_sign)

        await asyncio.sleep(random.uniform(0, 1))

    await RoverSign.upsert_rover_sign(rover_sign)

    return form_result


async def single_task(
    bot_id: str,
    uid: str,
    gid: str,
    qid: str,
    ck: str,
    private_msgs: Dict,
    group_msgs: Dict,
    all_msgs: Dict,
):
    im = await do_single_task(uid, ck)
    if isinstance(im, dict):
        msg = []
        msg.append(f"特征码: {uid}")
        for i, r in im.items():
            if r:
                msg.append(f"{i}: 成功")
            else:
                msg.append(f"{i}: 失败")

        im = "\n".join(msg)
    elif isinstance(im, bool):
        if im:
            im = "社区签到成功"
        else:
            im = "社区签到失败"
    else:
        return

    logger.debug(f"[鸣潮][社区签到]签到结果 uid: {uid} res: {im}")

    if gid == "on":
        if qid not in private_msgs:
            private_msgs[qid] = []
        private_msgs[qid].append(
            {"bot_id": bot_id, "uid": uid, "msg": [MessageSegment.text(im)]}
        )
        if "失败" in im:
            all_msgs["failed"] += 1
        else:
            all_msgs["success"] += 1
    elif gid == "off":
        if "失败" in im:
            all_msgs["failed"] += 1
        else:
            all_msgs["success"] += 1
    else:
        # 向群消息推送列表添加这个群
        if gid not in group_msgs:
            group_msgs[gid] = {
                "bot_id": bot_id,
                "success": 0,
                "failed": 0,
                "push_message": [],
            }

        if "失败" in im:
            all_msgs["failed"] += 1
            group_msgs[gid]["failed"] += 1
            group_msgs[gid]["push_message"].extend(
                [
                    MessageSegment.text("\n"),
                    MessageSegment.at(qid),
                    MessageSegment.text(im),
                ]
            )
        else:
            all_msgs["success"] += 1
            group_msgs[gid]["success"] += 1


async def single_daily_sign(
    bot_id: str,
    uid: str,
    gid: str,
    qid: str,
    ck: str,
    private_msgs: Dict,
    group_msgs: Dict,
    all_msgs: Dict,
):
    im = await sign_in(uid, ck)
    if gid == "on":
        if qid not in private_msgs:
            private_msgs[qid] = []
        private_msgs[qid].append(
            {"bot_id": bot_id, "uid": uid, "msg": [MessageSegment.text(im)]}
        )
        if "失败" in im:
            all_msgs["failed"] += 1
        elif "已签到" not in im:
            all_msgs["success"] += 1
    elif gid == "off":
        if "失败" in im:
            all_msgs["failed"] += 1
        elif "已签到" not in im:
            all_msgs["success"] += 1
    else:
        # 向群消息推送列表添加这个群
        if gid not in group_msgs:
            group_msgs[gid] = {
                "bot_id": bot_id,
                "success": 0,
                "failed": 0,
                "push_message": [],
            }
        if "失败" in im:
            all_msgs["failed"] += 1
            group_msgs[gid]["failed"] += 1
            group_msgs[gid]["push_message"].extend(
                [
                    MessageSegment.text("\n"),
                    MessageSegment.at(qid),
                    MessageSegment.text(im),
                ]
            )
        elif "已签到" not in im:
            all_msgs["success"] += 1
            group_msgs[gid]["success"] += 1


async def single_pgr_daily_sign(
    bot_id: str,
    uid: str,
    pgr_uid: str,
    gid: str,
    qid: str,
    ck: str,
    private_msgs: Dict,
    group_msgs: Dict,
    all_msgs: Dict,
):
    """战双游戏签到（用于自动签到任务）"""
    im = await pgr_sign_in(uid, pgr_uid, ck)
    if gid == "on":
        if qid not in private_msgs:
            private_msgs[qid] = []
        private_msgs[qid].append(
            {"bot_id": bot_id, "uid": pgr_uid, "msg": [MessageSegment.text(im)]}
        )
        if "失败" in im:
            all_msgs["failed"] += 1
        elif "已签到" not in im:
            all_msgs["success"] += 1
    elif gid == "off":
        if "失败" in im:
            all_msgs["failed"] += 1
        elif "已签到" not in im:
            all_msgs["success"] += 1
    else:
        # 向群消息推送列表添加这个群
        if gid not in group_msgs:
            group_msgs[gid] = {
                "bot_id": bot_id,
                "success": 0,
                "failed": 0,
                "push_message": [],
            }
        if "失败" in im:
            all_msgs["failed"] += 1
            group_msgs[gid]["failed"] += 1
            group_msgs[gid]["push_message"].extend(
                [
                    MessageSegment.text("\n"),
                    MessageSegment.at(qid),
                    MessageSegment.text(f"[战双] {im}"),
                ]
            )
        elif "已签到" not in im:
            all_msgs["success"] += 1
            group_msgs[gid]["success"] += 1


async def sign_in(uid: str, ck: str, isForce: bool = False) -> str:
    """鸣潮游戏签到"""
    from ..utils.api.api import WAVES_GAME_ID

    hasSignIn = False
    if not isForce:
        # 获取签到状态
        res = await rover_api.sign_in_task_list(uid, ck, gameId=WAVES_GAME_ID)
        if res.success and res.data and isinstance(res.data, dict):
            hasSignIn = res.data.get("isSigIn", False)

        if hasSignIn:
            # 已经签到
            await RoverSign.upsert_rover_sign(RoverSignData.build_game_sign(uid))
            logger.debug(f"UID{uid} 该用户今日已签到,跳过...")
            return "今日已签到！请勿重复签到！"

    sign_in_res = await rover_api.sign_in(uid, ck, gameId=WAVES_GAME_ID)
    if sign_in_res.success:
        # 签到成功
        await RoverSign.upsert_rover_sign(RoverSignData.build_game_sign(uid))
        return "签到成功！"
    elif sign_in_res.code == 1511:
        # 已经签到
        await RoverSign.upsert_rover_sign(RoverSignData.build_game_sign(uid))
        logger.debug(f"UID{uid} 该用户今日已签到,跳过...")
        return "今日已签到！请勿重复签到！"

    # 签到失败
    return "签到失败！"


async def pgr_sign_in(uid: str, pgr_uid: str, ck: str, isForce: bool = False) -> str:
    """战双游戏签到"""
    from ..utils.api.api import PGR_GAME_ID

    # 先获取角色列表，获取正确的 serverId
    logger.debug(f"[pgr_sign_in] 调用 find_role_list - gameId: {PGR_GAME_ID}")
    role_list_res = await rover_api.find_role_list(ck, PGR_GAME_ID)
    logger.debug(f"[pgr_sign_in] find_role_list 返回 - success: {role_list_res.success}, code: {role_list_res.code}, msg: {role_list_res.msg}")

    if not role_list_res.success:
        logger.error(f"[战双签到] 获取角色列表失败: {role_list_res.msg}")
        return f"签到失败：{role_list_res.msg}"

    if not role_list_res.data or not isinstance(role_list_res.data, list):
        logger.error(f"[战双签到] 角色列表为空 - data type: {type(role_list_res.data)}")
        return "签到失败：未绑定战双账号"

    logger.debug(f"[pgr_sign_in] 角色列表数量: {len(role_list_res.data)}")

    # 查找匹配的角色
    pgr_role = None
    for role in role_list_res.data:
        logger.debug(f"[pgr_sign_in] 检查角色 - roleId: {role.get('roleId')}, roleName: {role.get('roleName')}")
        if str(role.get("roleId")) == str(pgr_uid):
            pgr_role = role
            break

    if not pgr_role:
        logger.error(f"[战双签到] 未找到匹配的角色 UID: {pgr_uid}, 可用角色: {[r.get('roleId') for r in role_list_res.data]}")
        return "签到失败：未找到匹配的战双角色"

    server_id = pgr_role.get("serverId")
    logger.info(f"[战双签到] UID: {pgr_uid}, serverId: {server_id}, serverName: {pgr_role.get('serverName')}, roleName: {pgr_role.get('roleName')}")

    hasSignIn = False
    if not isForce:
        # 获取签到状态
        logger.debug(f"[pgr_sign_in] 调用 sign_in_task_list 检查签到状态 - pgr_uid: {pgr_uid}, gameId: {PGR_GAME_ID}, serverId: {server_id}")
        res = await rover_api.sign_in_task_list(pgr_uid, ck, gameId=PGR_GAME_ID, serverId=server_id)
        logger.debug(f"[pgr_sign_in] sign_in_task_list 返回 - success: {res.success}, code: {res.code}, msg: {res.msg}, data: {res.data}")

        if res.success and res.data and isinstance(res.data, dict):
            hasSignIn = res.data.get("isSigIn", False)
            logger.debug(f"[pgr_sign_in] 已签到状态: {hasSignIn}")

        if hasSignIn:
            # 已经签到
            await RoverSign.upsert_rover_sign(RoverSignData.build_pgr_game_sign(uid, pgr_uid))
            logger.debug(f"PGR UID{pgr_uid} 该用户今日已签到,跳过...")
            return "今日已签到！请勿重复签到！"

    logger.debug(f"[pgr_sign_in] 调用 sign_in 执行签到 - pgr_uid: {pgr_uid}, gameId: {PGR_GAME_ID}, serverId: {server_id}")
    sign_in_res = await rover_api.sign_in(pgr_uid, ck, gameId=PGR_GAME_ID, serverId=server_id)
    logger.debug(f"[pgr_sign_in] sign_in 返回 - success: {sign_in_res.success}, code: {sign_in_res.code}, msg: {sign_in_res.msg}, data: {sign_in_res.data}")

    if sign_in_res.success:
        # 签到成功
        await RoverSign.upsert_rover_sign(RoverSignData.build_pgr_game_sign(uid, pgr_uid))
        logger.debug("[pgr_sign_in] 签到成功")
        return "签到成功！"
    elif sign_in_res.code == 1511:
        # 已经签到
        await RoverSign.upsert_rover_sign(RoverSignData.build_pgr_game_sign(uid, pgr_uid))
        logger.debug("[pgr_sign_in] 今日已签到 (code 1511)")
        return "今日已签到！请勿重复签到！"

    # 签到失败
    logger.error(f"[战双签到] 签到失败: code={sign_in_res.code}, msg={sign_in_res.msg}, data={sign_in_res.data}")
    return f"签到失败：{sign_in_res.msg}"


def create_gradient_background(width, height, start_color, end_color=(255, 255, 255)):
    """
    使用 PIL 创建渐变背景
    start_color: 起始颜色，如 (230, 230, 255) 浅蓝
    end_color: 结束颜色，默认白色
    """
    # 创建新图像
    image = Image.new("RGB", (width, height))

    for y in range(height):
        # 计算当前行的颜色比例
        ratio = y / height

        # 计算当前行的 RGB 值
        r = int(end_color[0] * ratio + start_color[0] * (1 - ratio))
        g = int(end_color[1] * ratio + start_color[1] * (1 - ratio))
        b = int(end_color[2] * ratio + start_color[2] * (1 - ratio))

        # 创建当前行的颜色
        line_color = (r, g, b)
        # 绘制当前行
        for x in range(width):
            image.putpixel((x, y), line_color)

    return image


def create_sign_info_image(text, theme="blue"):
    text = text[1:]
    # 创建图片
    width = 600
    height = 250  # 稍微减小高度使布局更紧凑

    # 预定义主题颜色
    themes = {
        "blue": (230, 230, 255),  # 浅蓝
        "yellow": (255, 255, 230),  # 浅黄
        "pink": (255, 230, 230),  # 浅粉
        "green": (230, 255, 230),  # 浅绿
    }

    # 获取主题颜色，默认浅蓝
    start_color = themes.get(theme, themes["blue"])

    # 创建渐变背景
    img = create_gradient_background(width, height, start_color)
    draw = ImageDraw.Draw(img)

    # 颜色定义
    title_color = (51, 51, 51)  # 标题色

    # 绘制装饰边框
    border_color = (200, 200, 200)
    draw.rectangle([(10, 10), (width - 10, height - 10)], outline=border_color, width=2)

    # 文本处理
    lines = text.split("\n")
    left_margin = 40  # 左边距
    y = 40  # 起始y坐标

    for i, line in enumerate(lines):
        draw.text((left_margin, y), line, font=waves_font_24, fill=title_color)
        if i == 0:
            y += 60
        else:
            y += 45

    return img
