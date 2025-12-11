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
        "用户鸣潮游戏签到开关",
        "用户鸣潮游戏签到开关",
        False,
    ),
    "UserPGRSignin": GsBoolConfig(
        "用户战双游戏签到开关",
        "用户战双游戏签到开关",
        False,
    ),
    "UserBBSSchedSignin": GsBoolConfig(
        "用户库街区每日任务开关",
        "用户库街区每日任务开关",
        False,
    ),
    "SigninMaster": GsBoolConfig(
        "全部开启签到",
        "开启后自动帮登录的人签到",
        False,
    ),
    "SchedSignin": GsBoolConfig(
        "定时签到",
        "定时签到",
        False,
    ),
    "BBSSchedSignin": GsBoolConfig(
        "定时库街区每日任务",
        "定时库街区每日任务",
        False,
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
        "每晚签到时间设置",
        "每晚库街区签到时间设置（时，分）",
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
        "库洛域名代理（重启生效）",
        "库洛域名代理（重启生效）",
        "",
    ),
    "LocalProxyUrl": GsStrConfig(
        "本地代理地址",
        "本地代理地址",
        "",
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
}
