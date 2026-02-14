import asyncio
import random

from gsuid_core.gss import gss
from gsuid_core.logger import logger
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.boardcast.models import BoardCastMsgDict
from gsuid_core.utils.database.models import Subscribe

from ..utils.constant import BoardcastType
from ..utils.database.rover_subscribe import RoverSubscribe


async def send_board_cast_msg(
    msgs: BoardCastMsgDict, board_cast_type: BoardcastType
):
    logger.info(f"[推送] {board_cast_type} 任务启动...")
    private_msg_list = msgs["private_msg_dict"]
    group_msg_list = msgs["group_msg_dict"]

    subs = await gs_subscribe.get_subscribe(board_cast_type)

    def get_private_bot_self_id(qid, bot_id):
        """从 Subscribe 表获取私聊订阅的 bot_self_id"""
        if not subs:
            return ""
        for sub in subs:
            sub: Subscribe
            if sub.user_type != "direct":
                continue
            if sub.user_id == qid and sub.bot_id == bot_id:
                return sub.bot_self_id
        return ""

    # 执行私聊推送
    for qid in private_msg_list:
        try:
            for bot_id in gss.active_bot:
                for single in private_msg_list[qid]:
                    bot_self_id = get_private_bot_self_id(
                        qid, single["bot_id"]
                    )
                    await gss.active_bot[bot_id].target_send(
                        single["messages"],
                        "direct",
                        qid,
                        single["bot_id"],
                        bot_self_id,
                        "",
                    )
        except Exception as e:
            logger.exception(f"[推送] {qid} 私聊推送失败!错误信息", e)
        await asyncio.sleep(0.5 + random.randint(1, 3))
    logger.info(f"[推送] {board_cast_type} 私聊推送完成!")

    # 执行群聊推送
    for gid in group_msg_list:
        try:
            # 从 RoverSubscribe 获取该群绑定的 bot_self_id
            bot_self_id = await RoverSubscribe.get_group_bot(gid)
            if not bot_self_id:
                # fallback: 从消息中获取
                if isinstance(group_msg_list[gid], list):
                    bot_self_id = group_msg_list[gid][0].get("bot_id", "")
                else:
                    bot_self_id = group_msg_list[gid].get("bot_id", "")

            if not bot_self_id:
                logger.warning(f"[推送] 群 {gid} 无法获取 bot_self_id，跳过")
                continue

            for ws_bot_id in gss.active_bot:
                if isinstance(group_msg_list[gid], list):
                    for group in group_msg_list[gid]:
                        await gss.active_bot[ws_bot_id].target_send(
                            group["messages"],
                            "group",
                            gid,
                            group.get("bot_id", "onebot"),
                            bot_self_id,
                            "",
                        )
                        await asyncio.sleep(0.5 + random.randint(1, 3))
                else:
                    await gss.active_bot[ws_bot_id].target_send(
                        group_msg_list[gid]["messages"],
                        "group",
                        gid,
                        group_msg_list[gid].get("bot_id", "onebot"),
                        bot_self_id,
                        "",
                    )
        except Exception as e:
            logger.exception(f"[推送] 群 {gid} 推送失败!错误信息", e)
        await asyncio.sleep(0.5 + random.randint(1, 3))
    logger.info(f"[推送] {board_cast_type} 群聊推送完成!")
    logger.info(f"[推送] {board_cast_type} 任务结束!")
