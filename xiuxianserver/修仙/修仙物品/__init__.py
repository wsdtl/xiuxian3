"""修仙物品详情 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd=("查看修仙物品", "修仙物品查看", "查看"), priority=100, block=True)
async def ws_treasure_info(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看任意修仙物品详情。"""

    await send_reply(player_id, service.info(player_id, message), manager, service)
