"""二手市场组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd=("二手市场", "小黄鱼"), priority=100, block=True)
async def ws_second_hand_list(player_id: str = Depends(current_player_id)) -> None:
    """查看二手市场。"""

    await send_reply(player_id, service.list_items(player_id), manager, service)


@MessageHandler.handler(cmd=("二手市场上架", "小黄鱼上架"), priority=100, block=True)
async def ws_second_hand_sell(message: str, player_id: str = Depends(current_player_id)) -> None:
    """上架商品。"""

    await send_reply(player_id, service.sell(player_id, message), manager, service)


@MessageHandler.handler(cmd=("二手市场下架", "小黄鱼下架"), priority=100, block=True)
async def ws_second_hand_cancel(player_id: str = Depends(current_player_id)) -> None:
    """下架商品。"""

    await send_reply(player_id, service.cancel(player_id), manager, service)


@MessageHandler.handler(cmd=("二手市场购买", "小黄鱼购买"), priority=100, block=True)
async def ws_second_hand_buy(message: str, player_id: str = Depends(current_player_id)) -> None:
    """购买商品。"""

    await send_reply(player_id, service.buy(player_id, message), manager, service)
