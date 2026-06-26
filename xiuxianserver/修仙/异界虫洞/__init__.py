"""异界虫洞组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="虫洞", priority=100, block=True)
async def ws_wormhole_status(player_id: str = Depends(current_player_id)) -> None:
    """查看当前异界虫洞。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd="虫洞状态", priority=100, block=True)
async def ws_wormhole_state(player_id: str = Depends(current_player_id)) -> None:
    """查看当前异界虫洞状态。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd="挑战虫洞", priority=100, block=True)
async def ws_wormhole_challenge(player_id: str = Depends(current_player_id)) -> None:
    """挑战当前虫洞 Boss。"""

    await send_reply(player_id, service.challenge(player_id), manager, service)


@MessageHandler.handler(cmd="虫洞排行", priority=100, block=True)
async def ws_wormhole_ranking(player_id: str = Depends(current_player_id)) -> None:
    """查看虫洞伤害排行。"""

    await send_reply(player_id, service.ranking(player_id), manager, service)


@MessageHandler.handler(cmd="虫洞奖励", priority=100, block=True)
async def ws_wormhole_reward(player_id: str = Depends(current_player_id)) -> None:
    """领取虫洞贡献奖励。"""

    await send_reply(player_id, service.reward(player_id), manager, service)
