"""玩家对战组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd="切磋", priority=100, block=True)
async def ws_spar(client_id: str, message: str) -> None:
    """发起切磋。"""

    await ws_manager.send(service.spar(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("接受切磋", "切磋接受"), priority=100, block=True)
async def ws_accept_spar(client_id: str, message: str) -> None:
    """接受切磋。"""

    await ws_manager.send(service.accept_spar(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("拒绝切磋", "切磋拒绝"), priority=100, block=True)
async def ws_reject_spar(client_id: str, message: str) -> None:
    """拒绝切磋。"""

    await ws_manager.send(service.reject_spar(client_id, message), client_id)


@WsMessageHandler.handler(cmd="赌约", priority=100, block=True)
async def ws_bet(client_id: str, message: str) -> None:
    """发起赌约。"""

    await ws_manager.send(service.bet(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("接受赌约", "赌约接受"), priority=100, block=True)
async def ws_accept_bet(client_id: str, message: str) -> None:
    """接受赌约。"""

    await ws_manager.send(service.accept_bet(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("拒绝赌约", "赌约拒绝"), priority=100, block=True)
async def ws_reject_bet(client_id: str, message: str) -> None:
    """拒绝赌约。"""

    await ws_manager.send(service.reject_bet(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("决斗记录", "记录决斗"), priority=100, block=True)
async def ws_duel_records(client_id: str, message: str) -> None:
    """查看决斗记录。"""

    await ws_manager.send(service.records(client_id), client_id)
