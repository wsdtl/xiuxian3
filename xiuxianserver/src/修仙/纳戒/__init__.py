"""纳戒组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd=("查看纳戒", "纳戒查看"), priority=100, block=True)
async def ws_ring_list(client_id: str, message: str) -> None:
    """查看纳戒。"""

    await ws_manager.send(service.list_items(client_id), client_id)


@WsMessageHandler.handler(cmd=("查看装备库", "装备库查看"), priority=100, block=True)
async def ws_ring_info(client_id: str, message: str) -> None:
    """查看装备库物品。"""

    await ws_manager.send(service.info(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("使用装备库", "装备库使用"), priority=100, block=True)
async def ws_ring_use(client_id: str, message: str) -> None:
    """使用纳戒恢复类物品。"""

    await ws_manager.send(service.use_item(client_id, message), client_id)


@WsMessageHandler.handler(cmd="洗髓", priority=100, block=True)
async def ws_ring_wash(client_id: str, message: str) -> None:
    """消耗洗髓液洗髓体质。"""

    await ws_manager.send(service.wash(client_id), client_id)
