"""首领组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd=("首领", "岁时情劫"), priority=100, block=True)
async def ws_seasonal_boss_status(player_id: str = Depends(current_player_id)) -> None:
    """查看今日岁时情劫。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd=("首领状态", "岁时情劫状态"), priority=100, block=True)
async def ws_seasonal_boss_state(player_id: str = Depends(current_player_id)) -> None:
    """查看今日岁时情劫状态。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd=("挑战首领", "挑战岁时情劫"), priority=100, block=True)
async def ws_seasonal_boss_challenge(player_id: str = Depends(current_player_id)) -> None:
    """挑战今日岁时情劫。"""

    await send_reply(player_id, service.challenge(player_id), manager, service)


@MessageHandler.handler(cmd=("首领排行", "岁时情劫排行"), priority=100, block=True)
async def ws_seasonal_boss_ranking(player_id: str = Depends(current_player_id)) -> None:
    """查看岁时情劫伤害排行。"""

    await send_reply(player_id, service.ranking(player_id), manager, service)


@MessageHandler.handler(cmd=("首领奖励", "岁时情劫奖励"), priority=100, block=True)
async def ws_seasonal_boss_reward(player_id: str = Depends(current_player_id)) -> None:
    """领取岁时情劫贡献奖励。"""

    await send_reply(player_id, service.reward(player_id), manager, service)
