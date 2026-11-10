import json

from gsuid_core.logger import logger
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from ..utils.resource.RESOURCE_PATH import CONFIG_PATH
from .config_default import CONFIG_DEFAULT


def _load_legacy_config():
    """3.0.0 之前的配置（无 SchedSigninGame）"""
    if not CONFIG_PATH.exists():
        return None
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict) or "SchedSigninGame" in raw:
        return None
    return raw


def _migrate_legacy_config(raw: dict):
    def on(key: str) -> bool:
        item = raw.get(key)
        return bool(item.get("data")) if isinstance(item, dict) else False

    # 旧版仅开「全部开启签到」时不会执行任何签到
    if on("SigninMaster") and not (
        on("SchedSignin") or on("BBSSchedSignin") or on("UserPGRSignin")
    ):
        RoverSignConfig.set_config("SigninMaster", False)
        logger.warning(
            "[库洛签到·配置] 旧版仅开启「全部开启签到」时实际不会签到，"
            "为保持升级前后行为一致已将「自动签到：全部账号」关闭，如需使用请重新开启"
        )
    else:
        logger.info("[库洛签到·配置] 配置项已更名，原有设置保持不变")

    RoverSignConfig.set_config(
        "SchedSigninGame", RoverSignConfig.get_config("SchedSigninGame").data
    )


_legacy_config = _load_legacy_config()

RoverSignConfig = StringConfig("RoverSign", CONFIG_PATH, CONFIG_DEFAULT)

if _legacy_config is not None:
    try:
        _migrate_legacy_config(_legacy_config)
    except Exception as e:
        logger.warning(f"[库洛签到·配置] 配置迁移失败: {e}")
