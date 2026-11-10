from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsIntConfig,
    GsListStrConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "UserWavesSignin": GsBoolConfig(
        "手动签到：鸣潮",
        "用户发送「签到」时签到鸣潮",
        False,
    ),
    "UserPGRSignin": GsBoolConfig(
        "手动签到：战双",
        "用户发送「签到」时签到战双",
        False,
    ),
    "UserBBSSchedSignin": GsBoolConfig(
        "手动签到：库街区任务",
        "用户发送「签到」时完成库街区任务",
        False,
    ),
    "SchedSignin": GsBoolConfig(
        "自动签到：游戏",
        "每天定时为「开启自动签到」的用户签到游戏",
        False,
    ),
    "BBSSchedSignin": GsBoolConfig(
        "自动签到：库街区任务",
        "每天定时为「开启自动签到」的用户完成库街区任务",
        False,
    ),
    "SigninMaster": GsBoolConfig(
        "自动签到：全部账号",
        "无需用户开启，每天定时为所有已登录账号签到游戏并完成库街区任务",
        False,
    ),
    "SigninMasterSkipInactive": GsBoolConfig(
        "全部账号签到时跳过不活跃账号",
        "依赖「活跃账号认定天数」",
        False,
    ),
    "SchedSigninGame": GsListStrConfig(
        "自动签到的游戏",
        "自动签到包含的游戏，取消勾选后不再自动签到该游戏",
        ["鸣潮", "战双"],
        options=["鸣潮", "战双"],
    ),
    "BBSLink": GsListStrConfig(
        "库街区任务列表",
        "库街区任务列表",
        ["bbs_sign", "bbs_detail", "bbs_like", "bbs_share"],
        options=[
            "bbs_sign",
            "bbs_detail",
            "bbs_like",
            "bbs_share"
        ],
    ),
    "SignTime": GsListStrConfig(
        "自动签到时间",
        "每天开始自动签到的时间（时，分）",
        ["3", "0"],
    ),
    "SigninConcurrentNum": GsIntConfig(
        "自动签到并发数量", "自动签到并发数量，用xw池子的不要高于5", 1, max_value=10
    ),
    "SigninConcurrentNumInterval": GsListStrConfig(
        "自动签到并发数量间隔，默认3-5秒",
        "自动签到并发数量间隔，默认3-5秒",
        ["3", "5"],
    ),
    "PrivateSignReport": GsBoolConfig(
        "签到私聊报告",
        "关闭后将不再给任何人推送当天签到任务完成情况",
        False,
    ),
    "GroupSignReport": GsBoolConfig(
        "签到群组报告",
        "关闭后将不再给任何群推送当天签到任务完成情况",
        False,
    ),
    "GroupSignReportPic": GsBoolConfig(
        "签到群组图片报告",
        "签到以图片形式报告",
        False,
    ),
    "KuroUrlProxyUrl": GsStrConfig(
        "库洛域名代理（重载生效）",
        "库洛域名代理（重载生效）",
        "",
    ),
    "LocalProxyUrl": GsStrConfig(
        "本地代理地址",
        "本地代理地址",
        "",
        secret=True,
    ),
    "NeedProxyFunc": GsListStrConfig(
        "需要代理的函数",
        "需要代理的函数",
        ["all"],
        options=[
            "all",
            "do_sign_in",
        ],
    ),
    "RepeatSignin": GsBoolConfig(
        "反复签到",
        "开启后会在原定时签到基础上额外执行4次签到，一般每小时大约签800人（+9h、+12h、+13h、+14h）",
        False,
    ),
    "SignCompleteText": GsStrConfig(
        "签到完成文案",
        "签到完成时显示的文案",
        "✅ 已完成",
    ),
    "SignIncompleteText": GsStrConfig(
        "签到未完成文案",
        "签到未完成时显示的文案",
        "❌ 未完成",
    ),
    "SignSkipText": GsStrConfig(
        "签到跳过文案",
        "签到已跳过时显示的文案",
        "🚫 请勿重复签到",
    ),
    "ActiveUserDays": GsIntConfig(
        "活跃账号认定天数",
        "在此天数内有使用记录的账号被认定为活跃账号",
        42,
        10000,
    ),
    "SignActiveUserOnly": GsBoolConfig(
        "仅签到活跃账号",
        "开启后仅对活跃账号进行签到（需配合活跃账号认定天数使用）",
        False,
    ),
    "HideUid": GsBoolConfig(
        "隐藏uid",
        "开启后，所有渲染卡片中显示的UID将以 前2位 + **** + 后2位 的形式显示",
        False,
    ),
}
