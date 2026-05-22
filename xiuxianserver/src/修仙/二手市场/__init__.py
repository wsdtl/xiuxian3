"""二手市场组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd="二手市场", priority=100, block=True)
async def ws_second_hand_list(client_id: str, message: str) -> None:
    """查看二手市场。"""

    await ws_manager.send(service.list_items(client_id), client_id)


@WsMessageHandler.handler(cmd=("二手市场上架", "上架二手市场"), priority=100, block=True)
async def ws_second_hand_sell(client_id: str, message: str) -> None:
    """上架商品。"""

    await ws_manager.send(service.sell(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("二手市场下架", "下架二手市场"), priority=100, block=True)
async def ws_second_hand_cancel(client_id: str, message: str) -> None:
    """下架商品。"""

    await ws_manager.send(service.cancel(client_id), client_id)


@WsMessageHandler.handler(cmd=("二手市场购买", "购买二手市场"), priority=100, block=True)
async def ws_second_hand_buy(client_id: str, message: str) -> None:
    """购买商品。"""

    await ws_manager.send(service.buy(client_id, message), client_id)
