from abc import ABC, abstractmethod
from typing import Callable


class BaseAdapter(ABC):
    """通信或外部系统适配器基类。

    后台模板默认不携带具体驱动。后续接入 WS、MQ、机器人协议、
    webhook 等能力时，实现本基类并在 launch.mount.AdapterMount 中挂载。
    """

    @staticmethod
    @abstractmethod
    async def run() -> None:
        """启动适配器或整理运行期索引。"""

    @staticmethod
    @abstractmethod
    async def dispatch(*args, **kwargs) -> None:
        """分发消息、事件或外部请求。"""

    @staticmethod
    @abstractmethod
    def handler(*args, **kwargs) -> Callable:
        """注册处理函数。"""

    @staticmethod
    @abstractmethod
    async def shutdown() -> None:
        """关闭适配器并清理资源。"""


class BaseMessageHandler(BaseAdapter):
    """消息处理器基类。

    保留这个名称给 WS、机器人协议、MQ 等消息型 Adapter 使用。

    这里的约束只作为驱动器实现参考，不提供通用分发运行时。
    每个驱动器应该独立维护自己的 handler、dispatch、manager 和队列策略。

    项目业务函数建议接收的上下文字段：
    - client_id: 触发消息的玩家身份。
    - message: 命令触发片段之后的文本。
    - manager: 当前驱动器的回复器。
    - cmd: 命令片段。
    - raw_message: 完整原始文本。
    - message_data: 驱动器规整后的消息对象。
    - match: 正则命中对象；精确命令时为 None。

    回复器建议实现：
        async def send(message, client_id, is_log=True, request_id=None) -> bool
    """
