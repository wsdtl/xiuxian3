"""探险组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


@WsMessageHandler.handler(cmd=("地点", "位置"), priority=100, block=True)
async def ws_current_location(client_id: str, message: str) -> None:
    """查看当前位置。"""

    await send_reply(client_id, service.current_location(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="地点列表", priority=100, block=True)
async def ws_exploration_locations(client_id: str, message: str) -> None:
    """查看探险地点。"""

    await send_reply(client_id, service.locations(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("探险", "探索"), priority=100, block=True)
async def ws_exploration_start(client_id: str, message: str) -> None:
    """开始探险。"""

    await send_reply(client_id, service.start(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd=("探险状态", "状态探险", "探索状态"), priority=100, block=True)
async def ws_exploration_status(client_id: str, message: str) -> None:
    """查看探险状态。"""

    await send_reply(client_id, service.status(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("结束探险", "探险结束", "结束探索", "探索结束"), priority=100, block=True)
async def ws_exploration_claim(client_id: str, message: str) -> None:
    """领取探险结果。"""

    await send_reply(client_id, service.claim(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("掉落记录", "记录掉落"), priority=100, block=True)
async def ws_exploration_records(client_id: str, message: str) -> None:
    """查看探险记录。"""

    await send_reply(client_id, service.records(client_id), ws_manager, service)
