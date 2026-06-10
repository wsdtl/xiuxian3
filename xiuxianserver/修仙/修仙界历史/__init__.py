"""修仙界历史 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


@WsMessageHandler.handler(cmd="风云榜", priority=100, block=True)
async def ws_history_leaderboard(client_id: str, message: str) -> None:
    """查看风云榜。"""

    await send_reply(client_id, service.leaderboard(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="修仙早报", priority=100, block=True)
async def ws_history_morning_paper(client_id: str, message: str) -> None:
    """查看今日修仙早报。"""

    await send_reply(client_id, service.newspaper(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="修仙界历史", priority=100, block=True)
async def ws_history_chronicle(client_id: str, message: str) -> None:
    """查看最近修仙界历史。"""

    await send_reply(client_id, service.chronicle(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="人物志", priority=100, block=True)
async def ws_history_profile(client_id: str, message: str, raw_message: str,message_data) -> None:
    """查看公开人物志。"""

    await send_reply(client_id, service.profile(client_id, message), ws_manager, service)
