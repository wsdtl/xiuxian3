"""背包组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="背包", priority=100, block=True)
async def ws_backpack_list(player_id: str = Depends(current_player_id)) -> None:
    """查看背包。"""

    await send_reply(player_id, service.list_items(player_id), manager, service)


@MessageHandler.handler(cmd="使用", priority=100, block=True)
async def ws_backpack_use(message: str, player_id: str = Depends(current_player_id)) -> None:
    """使用物品。"""

    await send_reply(player_id, service.use_item(player_id, message), manager, service)
