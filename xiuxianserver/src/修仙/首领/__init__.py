"""首领组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


# 需要临时给今天补一只最近已过的岁时情劫时，再取消下面这个启动回调的注释。
# 同为 priority=50 时，修仙根入口会先初始化数据库，本回调随后执行。
# from launch import OnEvent
#
# @OnEvent.connect(priority=50)
# async def start_recent_past_boss() -> None:
#     """服务启动时临时补生成最近已过的岁时情劫。"""
#
#     service.open_recent_past_event_for_today()


@WsMessageHandler.handler(cmd=("首领", "岁时情劫"), priority=100, block=True)
async def ws_seasonal_boss_status(client_id: str, message: str) -> None:
    """查看今日岁时情劫。"""

    await send_reply(client_id, service.status(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("首领状态", "状态首领"), priority=100, block=True)
async def ws_seasonal_boss_status_alias(client_id: str, message: str) -> None:
    """查看今日岁时情劫状态。"""

    await send_reply(client_id, service.status(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("挑战首领", "首领挑战"), priority=100, block=True)
async def ws_seasonal_boss_challenge(client_id: str, message: str) -> None:
    """挑战今日岁时情劫。"""

    await send_reply(client_id, service.challenge(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("首领排行", "排行首领"), priority=100, block=True)
async def ws_seasonal_boss_ranking(client_id: str, message: str) -> None:
    """查看岁时情劫伤害排行。"""

    await send_reply(client_id, service.ranking(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("首领奖励", "奖励首领"), priority=100, block=True)
async def ws_seasonal_boss_reward(client_id: str, message: str) -> None:
    """领取岁时情劫贡献奖励。"""

    await send_reply(client_id, service.reward(client_id), ws_manager, service)
