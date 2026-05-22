from typing import Callable
from abc import abstractmethod


class BaseMessageHandler:
    """消息处理器基类。"""

    @abstractmethod
    async def run() -> None:
        """启动处理器。"""
        pass

    @abstractmethod
    async def dispatch(*args, **kwargs) -> None:
        """分发消息。"""
        pass

    @abstractmethod
    def handler(*args, **kwargs) -> Callable:
        """注册处理函数。"""
        pass

    @abstractmethod
    async def shutdown() -> None:
        """关闭并清理资源。"""
        pass
