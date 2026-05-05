"""
签到状态文件管理模块
用于记录和恢复签到任务状态，支持重启后继续执行
"""
import json
from typing import Optional, Literal
from datetime import datetime

from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger

# 状态文件路径
DATA_PATH = get_res_path() / "RoverSign"
STATE_FILE = DATA_PATH / "signing_state.json"

SignType = Literal["auto", "manual"]  # auto=自动签到, manual=全部签到


class SigningState:
    """签到状态管理类"""

    def __init__(self):
        self.ensure_data_dir()

    @staticmethod
    def ensure_data_dir():
        """确保数据目录存在"""
        DATA_PATH.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_signing() -> bool:
        """检查是否正在签到"""
        return STATE_FILE.exists()

    @staticmethod
    def get_state() -> Optional[dict]:
        """获取当前签到状态。返回 {"type", "start_time"} 或 None。"""
        if not STATE_FILE.exists():
            return None

        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.debug(f"[SignState] 读取状态文件: {state}")
            return state
        except Exception as e:
            logger.error(f"[SignState] 读取状态文件失败: {e}")
            return None

    @staticmethod
    def set_state(sign_type: SignType):
        """设置签到状态。"""
        state = {
            "type": sign_type,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info(f"[SignState] 创建状态文件: type={sign_type}")
        except Exception as e:
            logger.error(f"[SignState] 创建状态文件失败: {e}")

    @staticmethod
    def clear_state():
        """清除签到状态（签到完成时调用）"""
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
                logger.info("[SignState] 删除状态文件（签到已完成）")
            except Exception as e:
                logger.error(f"[SignState] 删除状态文件失败: {e}")

    @staticmethod
    def should_resume() -> bool:
        """
        检查是否应该恢复签到任务

        Returns:
            bool: True 表示需要恢复签到
        """
        if not STATE_FILE.exists():
            return False

        state = SigningState.get_state()
        if not state:
            return False

        # 检查状态文件是否过期（超过24小时视为无效）
        try:
            start_time = datetime.strptime(state["start_time"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            elapsed = (now - start_time).total_seconds()

            if elapsed > 86400:  # 24小时
                logger.warning(f"[SignState] 状态文件已过期（{elapsed/3600:.1f}小时），清除")
                SigningState.clear_state()
                return False

            logger.info(f"[SignState] 发现未完成的签到任务: type={state['type']}, elapsed={elapsed/60:.1f}分钟")
            return True
        except Exception as e:
            logger.error(f"[SignState] 检查状态文件时出错: {e}")
            return False


# 创建全局实例
signing_state = SigningState()
