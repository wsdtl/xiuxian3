"""探险组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="位置", priority=100, block=True)
async def ws_current_location(player_id: str = Depends(current_player_id)) -> None:
    """查看当前位置。"""

    await send_reply(player_id, service.current_location(player_id), manager, service)


@MessageHandler.handler(cmd=("探险列表", "地图"), priority=100, block=True)
async def ws_exploration_locations(player_id: str = Depends(current_player_id)) -> None:
    """查看探险地点。"""

    await send_reply(player_id, service.locations(player_id), manager, service)


@MessageHandler.handler(cmd="探险", priority=100, block=True)
async def ws_exploration_start(message: str, player_id: str = Depends(current_player_id)) -> None:
    """开始探险。"""

    await send_reply(player_id, service.start(player_id, message), manager, service)


@MessageHandler.handler(cmd="探险状态", priority=100, block=True)
async def ws_exploration_status(player_id: str = Depends(current_player_id)) -> None:
    """查看探险状态。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd=("结束探险", "探险结束"), priority=100, block=True)
async def ws_exploration_claim(player_id: str = Depends(current_player_id)) -> None:
    """领取探险结果。"""

    await send_reply(player_id, service.claim(player_id), manager, service)


@MessageHandler.handler(cmd="探险记录", priority=100, block=True)
async def ws_exploration_records(player_id: str = Depends(current_player_id)) -> None:
    """查看探险记录。"""

    await send_reply(player_id, service.records(player_id), manager, service)
