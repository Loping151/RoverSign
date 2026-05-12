from PIL import Image

from gsuid_core.bot import Bot
from gsuid_core.help.utils import register_help
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix

from .get_help import ICON, get_help

sv_rover_help = SV("RoverSign帮助", priority=10)


@sv_rover_help.on_fullmatch(
    "帮助",
    to_ai="""返回 RoverSign（鸣潮库街区签到）插件的命令帮助图。

当用户问「rs 帮助 / 签到帮助 / 鸣潮签到怎么用 / rover sign help」时调用。

Args:
    text: 无需参数。
""",
)
async def send_help_img(bot: Bot, ev: Event):
    await bot.send(await get_help(ev.user_pm))


PREFIX = get_plugin_available_prefix("RoverSign")
register_help("RoverSignUID", f"{PREFIX}帮助", Image.open(ICON))
