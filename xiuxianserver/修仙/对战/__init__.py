"""玩家对战组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="切磋", priority=100, block=True)
async def ws_spar(message: str, player_id: str = Depends(current_player_id)) -> None:
    """发起切磋。"""

    await send_reply(player_id, service.spar(player_id, message), manager, service)


@MessageHandler.handler(cmd="接受切磋", priority=100, block=True)
async def ws_accept_spar(message: str, player_id: str = Depends(current_player_id)) -> None:
    """接受切磋。"""

    await send_reply(player_id, service.accept_spar(player_id, message), manager, service)


@MessageHandler.handler(cmd="拒绝切磋", priority=100, block=True)
async def ws_reject_spar(message: str, player_id: str = Depends(current_player_id)) -> None:
    """拒绝切磋。"""

    await send_reply(player_id, service.reject_spar(player_id, message), manager, service)


@MessageHandler.handler(cmd="决斗", priority=100, block=True)
async def ws_duel(message: str, player_id: str = Depends(current_player_id)) -> None:
    """发起押注决斗。"""

    await send_reply(player_id, service.duel(player_id, message), manager, service)


@MessageHandler.handler(cmd="接受决斗", priority=100, block=True)
async def ws_accept_duel(message: str, player_id: str = Depends(current_player_id)) -> None:
    """接受押注决斗。"""

    await send_reply(player_id, service.accept_duel(player_id, message), manager, service)


@MessageHandler.handler(cmd="拒绝决斗", priority=100, block=True)
async def ws_reject_duel(message: str, player_id: str = Depends(current_player_id)) -> None:
    """拒绝押注决斗。"""

    await send_reply(player_id, service.reject_duel(player_id, message), manager, service)


@MessageHandler.handler(cmd="决斗记录", priority=100, block=True)
async def ws_duel_records(player_id: str = Depends(current_player_id)) -> None:
    """查看切磋和决斗记录。"""

    await send_reply(player_id, service.records(player_id), manager, service)


@MessageHandler.handler(cmd="抢劫", priority=100, block=True)
async def ws_robbery(message: str, player_id: str = Depends(current_player_id)) -> None:
    """抢劫正在探险中的玩家。"""

    await send_reply(player_id, service.robbery(player_id, message), manager, service)
