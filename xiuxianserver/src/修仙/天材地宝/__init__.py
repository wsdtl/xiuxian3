"""天材地宝组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd=("查看天材地宝", "天材地宝查看"), priority=100, block=True)
async def ws_treasure_info(client_id: str, message: str) -> None:
    """查看物品库物品。"""

    await ws_manager.send(service.info(client_id, message), client_id)
