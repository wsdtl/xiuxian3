"""背包组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd=("查看背包", "背包查看"), priority=100, block=True)
async def ws_backpack_list(client_id: str, message: str) -> None:
    """查看背包。"""

    await ws_manager.send(service.list_items(client_id), client_id)


@WsMessageHandler.handler(cmd="使用", priority=100, block=True)
async def ws_backpack_use(client_id: str, message: str) -> None:
    """使用物品。"""

    await ws_manager.send(service.use_item(client_id, message), client_id)
