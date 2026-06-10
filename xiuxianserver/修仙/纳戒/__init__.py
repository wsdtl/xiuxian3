"""纳戒组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


@WsMessageHandler.handler(cmd="纳戒", priority=100, block=True)
async def ws_ring_list(client_id: str, message: str) -> None:
    """查看纳戒。"""

    await send_reply(client_id, service.list_items(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="洗髓", priority=100, block=True)
async def ws_ring_wash(client_id: str, message: str) -> None:
    """消耗洗髓液洗髓体质。"""

    await send_reply(client_id, service.wash(client_id), ws_manager, service)
