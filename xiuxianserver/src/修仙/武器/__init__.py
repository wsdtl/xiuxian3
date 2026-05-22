"""武器组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd="武器", priority=100, block=True)
async def ws_weapon_list(client_id: str, message: str) -> None:
    """查看武器。"""

    await ws_manager.send(service.list_weapons(client_id), client_id)


@WsMessageHandler.handler(cmd=("切换武器", "武器切换"), priority=100, block=True)
async def ws_weapon_switch(client_id: str, message: str) -> None:
    """切换武器。"""

    await ws_manager.send(service.switch(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("升级武器", "武器升级"), priority=100, block=True)
async def ws_weapon_upgrade(client_id: str, message: str) -> None:
    """升级武器。"""

    await ws_manager.send(service.upgrade(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("回收武器", "武器回收"), priority=100, block=True)
async def ws_weapon_recycle(client_id: str, message: str) -> None:
    """在回收地点处理备用武器。"""

    await ws_manager.send(service.recycle(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("附魔武器", "武器附魔"), priority=100, block=True)
async def ws_weapon_enchant(client_id: str, message: str) -> None:
    """附魔武器。"""

    await ws_manager.send(service.enchant(client_id, message), client_id)
