"""世界皮肤组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_is_master, current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="世界皮肤", priority=100, block=True)
async def ws_world_skin_info(
    player_id: str = Depends(current_player_id),
    is_master: bool = Depends(current_is_master),
) -> None:
    """查看当前世界皮肤。"""

    await send_reply(player_id, service.info(player_id, is_master=is_master), manager, service)


@MessageHandler.handler(cmd="世界皮肤切换", priority=100, block=True)
async def ws_world_skin_switch(
    message: str,
    player_id: str = Depends(current_player_id),
    is_master: bool = Depends(current_is_master),
) -> None:
    """切换世界皮肤。"""

    await send_reply(player_id, service.switch(player_id, message, is_master=is_master), manager, service)
