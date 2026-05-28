import asyncio
import inspect
import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from aiohttp import (
    ClientSession,
    ClientTimeout,
    ContentTypeError,
    FormData,
    TCPConnector,
)

from gsuid_core.logger import logger

from ..api.api import (
    FIND_ROLE_LIST_URL,
    FORUM_LIST_URL,
    PGR_GAME_ID,
    WAVES_GAME_ID,
    GET_TASK_URL,
    LIKE_URL,
    LOGIN_LOG_URL,
    MR_REFRESH_URL,
    POST_DETAIL_URL,
    REFRESH_URL,
    REQUEST_TOKEN,
    SERVER_ID,
    SERVER_ID_NET,
    SHARE_URL,
    SIGN_IN_URL,
    SIGNIN_TASK_LIST_URL,
    SIGNIN_URL,
    get_local_proxy_url,
    get_need_proxy_func,
)
from ..database.models import WavesUser
from ..errors import ROVER_CODE_999
from ..util import timed_async_cache
from .request_util import KURO_VERSION, KuroApiResp, get_base_header


class RoverRequest:
    ssl_verify = True

    def is_net(self, roleId):
        _temp = int(roleId)
        return _temp >= 200000000

    def get_server_id(
        self,
        roleId: str,
        serverId: Optional[str] = None,
        game_id: int = WAVES_GAME_ID,
    ) -> str:
        if serverId:
            return serverId
        if game_id == WAVES_GAME_ID:
            if self.is_net(roleId):
                return SERVER_ID_NET
            return SERVER_ID
        return ""

    async def refresh_bat_token(self, waves_user: WavesUser):
        success, access_token = await self.get_request_token(
            waves_user.uid,
            waves_user.cookie,
            waves_user.did,
            game_id=waves_user.game_id,
        )
        if not success:
            return waves_user

        waves_user.bat = access_token
        await WavesUser.update_data_by_data(
            select_data={
                "uid": waves_user.uid,
                "game_id": waves_user.game_id,
            },
            update_data={"bat": access_token},
        )
        return waves_user

    async def get_used_headers(
        self,
        cookie: str,
        uid: str,
        needToken: bool = False,
        game_id: Optional[int] = WAVES_GAME_ID,
    ) -> Dict[str, Any]:
        headers = {
            "did": "",
            "b-at": "",
        }
        if needToken:
            headers["token"] = cookie
        waves_user: Optional[WavesUser] = await WavesUser.select_data_by_cookie_and_uid(
            cookie=cookie,
            uid=uid,
            game_id=game_id,
        ) or await WavesUser.select_data_by_cookie(
            cookie=cookie,
        )

        if not waves_user:
            return headers

        headers["did"] = waves_user.did or ""
        headers["b-at"] = waves_user.bat or ""
        return headers

    async def get_self_waves_ck(
        self, uid: str, user_id: str, bot_id: str
    ) -> Optional[str]:
        # 返回空串 表示绑定已失效
        waves_user = await WavesUser.select_waves_user(uid, user_id, bot_id, game_id=WAVES_GAME_ID)
        if not waves_user or not waves_user.cookie:
            return ""

        if waves_user.status == "无效":
            return ""

        data = await self.login_log(uid, waves_user.cookie, game_id=WAVES_GAME_ID)
        if not data.success:
            await data.mark_cookie_invalid(uid, waves_user.cookie)
            return ""

        data = await self.refresh_data(uid, waves_user.cookie, game_id=WAVES_GAME_ID)
        if not data.success:
            if data.is_bat_token_invalid:
                if waves_user := await self.refresh_bat_token(waves_user):
                    return waves_user.cookie
            else:
                await data.mark_cookie_invalid(uid, waves_user.cookie)
            return ""

        return waves_user.cookie

    async def refresh_data(
        self,
        roleId: str,
        token: str,
        serverId: Optional[str] = None,
        game_id: int = WAVES_GAME_ID,
    ):
        """刷新数据"""
        if game_id == PGR_GAME_ID:
            # 战双没有对应的 aki refresh 接口，直接跳过
            return KuroApiResp.ok(True)
        header = await get_base_header()
        used_headers = await self.get_used_headers(cookie=token, uid=roleId, game_id=game_id)
        header.update(used_headers)
        data = {
            "gameId": game_id,
            "serverId": self.get_server_id(roleId, serverId, game_id=game_id),
            "roleId": roleId,
        }
        return await self._waves_request(REFRESH_URL, "POST", header, data=data)

    async def login_log(self, roleId: str, token: str, game_id: int = WAVES_GAME_ID):
        """登录校验"""
        header = await get_base_header()
        used_headers = await self.get_used_headers(cookie=token, uid=roleId, game_id=game_id)
        header.update(
            {
                "token": token,
                "devCode": used_headers.get("did", ""),
                "version": KURO_VERSION,
            }
        )

        data = {}
        return await self._waves_request(LOGIN_LOG_URL, "POST", header, data=data)

    async def get_request_token(
        self,
        roleId: str,
        token: str,
        did: str,
        serverId: Optional[str] = None,
        game_id: int = WAVES_GAME_ID,
    ) -> tuple[bool, str]:
        """请求token"""
        header = await get_base_header()
        header.update(
            {
                "token": token,
                "did": did,
                "b-at": "",
            }
        )
        if game_id == PGR_GAME_ID and not serverId:
            role_list_res = await self.find_role_list(token, game_id)
            if role_list_res.success and isinstance(role_list_res.data, list):
                for role in role_list_res.data:
                    if str(role.get("roleId")) == str(roleId):
                        serverId = role.get("serverId")
                        break
            if not serverId:
                logger.debug(
                    f"[库洛签到·请求token] 未能获取战双 serverId - roleId: {roleId}"
                )
                return False, ""
        data = {
            "serverId": self.get_server_id(roleId, serverId, game_id=game_id),
            "roleId": roleId,
        }
        raw_data = await self._waves_request(REQUEST_TOKEN, "POST", header, data=data)
        logger.debug(f"[库洛签到·请求token] raw_data: {raw_data}")
        if raw_data.success and isinstance(raw_data.data, dict):
            if accessToken := raw_data.data.get("accessToken", ""):
                return True, accessToken

        return False, ""

    async def get_daily_info(
        self, roleId: str, token: str, gameId: Union[str, int] = WAVES_GAME_ID
    ):
        """每日"""
        header = await get_base_header()
        used_headers = await self.get_used_headers(cookie=token, uid=roleId, game_id=gameId)
        header.update(used_headers)
        data = {
            "type": "1",
            "sizeType": "2",
            "gameId": gameId,
            "serverId": self.get_server_id(roleId, game_id=gameId),
            "roleId": roleId,
        }
        return await self._waves_request(
            MR_REFRESH_URL,
            "POST",
            header,
            data=data,
        )

    async def sign_in(
        self, roleId: str, token: str, gameId: int = WAVES_GAME_ID, serverId: Optional[str] = None
    ):
        """游戏签到"""
        header = await get_base_header()
        used_headers = await self.get_used_headers(
            cookie=token, uid=roleId, needToken=True, game_id=gameId
        )
        header.update(used_headers)
        header.update({"devcode": ""})
        data = {
            "gameId": gameId,
            "serverId": serverId or SERVER_ID,
            "roleId": roleId,
            "reqMonth": f"{datetime.now().month:02}",
        }
        return await self._waves_request(SIGNIN_URL, "POST", header, data=data)

    async def sign_in_task_list(
        self, roleId: str, token: str, gameId: int = WAVES_GAME_ID, serverId: Optional[str] = None
    ):
        """游戏签到任务列表"""
        header = await get_base_header()
        used_headers = await self.get_used_headers(
            cookie=token, uid=roleId, needToken=True, game_id=gameId
        )
        header.update(used_headers)
        header.update({"devcode": ""})
        data = {
            "gameId": gameId,
            "serverId": serverId or SERVER_ID,
            "roleId": roleId,
        }
        return await self._waves_request(
            SIGNIN_TASK_LIST_URL, "POST", header, data=data
        )

    async def find_role_list(self, token: str, gameId: int):
        """获取角色列表"""
        header = await get_base_header()
        used_headers = await self.get_used_headers(cookie=token, uid="", needToken=True, game_id=gameId)
        header.update(used_headers)
        data = {
            "gameId": gameId,
        }
        return await self._waves_request(
            FIND_ROLE_LIST_URL, "POST", header, data=data
        )

    async def get_task(self, token: str, roleId: str):
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(
                cookie=token, uid=roleId, needToken=True
            )
            header.update(used_headers)
            data = {"gameId": "0"}
            return await self._waves_request(GET_TASK_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"get_task token {token}", e)

    @timed_async_cache(
        3600,
        lambda x: x and isinstance(x, dict) and x.get("code") == 200,
    )
    async def get_form_list(self, token: str):
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(cookie=token, uid="")
            header.update(used_headers)
            header.update({"version": "2.25"})
            data = {
                "pageIndex": "1",
                "pageSize": "20",
                "timeType": "0",
                "searchType": "1",
                "forumId": "9",
                "gameId": "3",
            }
            return await self._waves_request(FORUM_LIST_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"get_form_list token {token}", e)

    # async def get_gold(self, token: str) -> Optional[Union[Dict, int, str]]:
    #     """获取金币"""
    #     try:
    #         header = await get_base_header()
    #         used_headers = await self.get_used_headers(cookie=token, uid="")
    #         header.update(used_headers)
    #         return await self._waves_request(GET_GOLD_URL, "POST", header)
    #     except Exception as e:
    #         logger.exception(f"get_gold token {token}", e)

    async def do_like(self, roleId: str, token: str, postId, toUserId):
        """点赞"""
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(
                cookie=token, uid=roleId, needToken=True
            )
            header.update(used_headers)
            data = {
                "gameId": "3",  # 鸣潮
                "likeType": "1",  # 1.点赞帖子 2.评论
                "operateType": "1",  # 1.点赞 2.取消
                "postId": postId,
                "toUserId": toUserId,
            }
            return await self._waves_request(LIKE_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"do_like token {token}", e)

    async def do_sign_in(self, roleId: str, token: str):
        """签到"""
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(
                cookie=token, uid=roleId, needToken=True
            )
            header.update(used_headers)
            data = {"gameId": "2"}
            return await self._waves_request(SIGN_IN_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"do_sign_in token {token}", e)

    async def do_post_detail(self, roleId: str, token: str, postId: str):
        """浏览"""
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(cookie=token, uid=roleId)
            header.update(
                {
                    "token": token,
                    "devCode": used_headers.get("did", ""),
                }
            )
            data = {
                "postId": postId,
                "showOrderType": "2",
                "isOnlyPublisher": "0",
            }
            return await self._waves_request(POST_DETAIL_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"do_post_detail token {token}", e)

    async def do_share(self, roleId: str, token: str):
        """分享"""
        try:
            header = await get_base_header()
            used_headers = await self.get_used_headers(
                cookie=token, uid=roleId, needToken=True
            )
            header.update(used_headers)
            data = {"gameId": "3"}
            return await self._waves_request(SHARE_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception(f"do_share token {token}", e)

    # async def check_bbs_completed(self, token: str, roleId: str) -> bool:
    #     """检查bbs任务是否完成"""
    #     task_res = await self.get_task(token, roleId)
    #     if not isinstance(task_res, dict):
    #         return False
    #     if task_res.get("code") != 200 or not task_res.get("data"):
    #         return False
    #     for i in task_res["data"]["dailyTask"]:
    #         if i["completeTimes"] != i["needActionTimes"]:
    #             return False
    #     return True

    async def _waves_request(
        self,
        url: str,
        method: Literal["GET", "POST"] = "GET",
        header: Optional[Mapping[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[FormData, Dict[str, Any]]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> KuroApiResp[Union[str, Dict[str, Any], List[Any]]]:
        if header is None:
            header = await get_base_header()

        proxy_func = get_need_proxy_func()
        if inspect.stack()[1].function in proxy_func or "all" in proxy_func:
            proxy_url = get_local_proxy_url()
        else:
            proxy_url = None

        for attempt in range(max_retries):
            try:
                async with ClientSession(
                    connector=TCPConnector(verify_ssl=self.ssl_verify)
                ) as client:
                    async with client.request(
                        method,
                        url=url,
                        headers=header,
                        params=params,
                        json=json_data,
                        data=data,
                        proxy=proxy_url,
                        timeout=ClientTimeout(10),
                    ) as resp:
                        try:
                            raw_data = await resp.json()
                        except ContentTypeError:
                            _raw_data = await resp.text()
                            raw_data = {"code": ROVER_CODE_999, "data": _raw_data}
                        if isinstance(raw_data, dict):
                            try:
                                raw_data["data"] = json.loads(raw_data.get("data", ""))
                            except Exception:
                                pass
                        logger.debug(
                            f"url:[{url}] params:[{params}] headers:[{header}] data:[{data}] raw_data:{raw_data}"
                        )
                        return KuroApiResp[Any].model_validate(raw_data)
            except Exception as e:
                logger.exception(f"url:[{url}] attempt {attempt + 1} failed", e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        return KuroApiResp[Any].err(
            "请求服务器失败，已达最大重试次数", code=ROVER_CODE_999
        )
