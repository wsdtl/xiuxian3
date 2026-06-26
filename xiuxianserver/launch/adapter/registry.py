from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from fastapi import APIRouter

from launch.config import config
from launch.log import C, logger

from .base_handler import BaseAdapter
from .depends import call_with_dependencies


_current_manager: ContextVar[Any | None] = ContextVar(
    "adapter_current_manager",
    default=None,
)


@dataclass(frozen=True)
class AdapterSpec:
    """一个可启用通信适配器的公共描述。"""

    name: str
    route: str
    router: APIRouter
    handler: type[BaseAdapter]
    manager: Any
    has_context: Callable[[], bool]


def available_adapter_specs() -> Dict[str, AdapterSpec]:
    """返回项目已接入的适配器清单。

    这里使用函数内导入，避免业务模块导入公共注册器时提前形成循环依赖。
    """

    from . import qq, ws
    from .qq.manager import current_event
    from .ws.manager import current_request_id

    return {
        "qq": AdapterSpec(
            name="qq",
            route=qq.QQ_EVENT_ROUTE,
            router=qq.router,
            handler=qq.QqEventHandler,
            manager=qq.manager,
            has_context=lambda: current_event.get() is not None,
        ),
        "ws": AdapterSpec(
            name="ws",
            route=ws.WS_ROUTE,
            router=ws.router,
            handler=ws.WsMessageHandler,
            manager=ws.manager,
            has_context=lambda: current_request_id.get() is not None,
        ),
    }


def enabled_adapter_names() -> List[str]:
    """读取配置中启用的适配器名称，并保持顺序去重。"""

    available = available_adapter_specs()
    names: List[str] = []

    for raw_name in config.adapter.enabled:
        name = raw_name.strip().lower()
        if not name:
            continue
        if name not in available:
            raise ValueError(f"未知通信适配器：{raw_name}")
        if name not in names:
            names.append(name)

    return names


def enabled_adapter_specs() -> List[AdapterSpec]:
    """返回当前启用的适配器描述。"""

    available = available_adapter_specs()
    return [available[name] for name in enabled_adapter_names()]


class MessageHandler:
    """把业务命令同时注册到当前启用的消息适配器。"""

    @staticmethod
    def handler(*args, **kwargs) -> Callable:
        def wrapper(func: Callable) -> Callable:
            for spec in enabled_adapter_specs():
                spec.handler.handler(*args, **kwargs)(
                    MessageHandler._bind_manager(func, spec.manager)
                )
            return func

        return wrapper

    @staticmethod
    def _bind_manager(func: Callable, real_manager: Any) -> Callable:
        async def wrapped(**context: Any) -> Any:
            token = _current_manager.set(context.get("manager") or real_manager)
            try:
                return await call_with_dependencies(func, context)
            finally:
                _current_manager.reset(token)

        return wrapped


class AdapterReplyManager:
    """根据当前消息上下文选择真实适配器回复器。"""

    async def send(
        self,
        message: object,
        client_id: str,
        is_log: bool = True,
        request_id: object | None = None,
    ) -> bool:
        manager = self._current_manager()
        if manager is None:
            if is_log:
                logger.opt(colors=True).warning(
                    f"{C.warn('回复失败，缺少当前适配器上下文')} {C.kv('client', client_id)}"
                )
            return False

        return await manager.send(
            message,
            client_id,
            is_log=is_log,
            request_id=request_id,
        )

    @staticmethod
    def _current_manager() -> Any | None:
        current = _current_manager.get()
        if current is not None:
            return current

        specs = enabled_adapter_specs()

        for spec in specs:
            if spec.has_context():
                return spec.manager

        if len(specs) == 1:
            return specs[0].manager
        return None


manager = AdapterReplyManager()
