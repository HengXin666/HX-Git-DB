"""提交消息格式化"""

from enum import Enum


class MsgType(Enum):
    """提交消息类型"""
    FEAT = "feat"
    FIX = "fix"

    def format(self, message: str) -> str:
        """格式化提交消息

        Args:
            message: 提交消息内容

        Returns:
            格式化后的提交消息, 如 "[feat] 添加新功能"
        """
        return f"[{self.value}] {message}"


DEFAULT_COMMIT_MSG = MsgType.FEAT.format("sync data")
