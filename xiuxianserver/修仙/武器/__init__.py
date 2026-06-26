"""武器组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="武器", priority=100, block=True)
async def ws_weapon_list(player_id: str = Depends(current_player_id)) -> None:
    """查看武器简表。"""

    await send_reply(player_id, service.list_weapons(player_id), manager, service)


@MessageHandler.handler(cmd="查看武器", priority=100, block=True)
async def ws_weapon_detail(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看单把武器详情。"""

    await send_reply(player_id, service.detail(player_id, message), manager, service)


@MessageHandler.handler(cmd="武器传奇", priority=100, block=True)
async def ws_weapon_legend(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看单把武器传奇记录。"""

    await send_reply(player_id, service.legend(player_id, message), manager, service)


@MessageHandler.handler(cmd="切换武器", priority=100, block=True)
async def ws_weapon_switch(message: str, player_id: str = Depends(current_player_id)) -> None:
    """切换武器。"""

    await send_reply(player_id, service.switch(player_id, message), manager, service)


@MessageHandler.handler(cmd="升级武器", priority=100, block=True)
async def ws_weapon_upgrade(message: str, player_id: str = Depends(current_player_id)) -> None:
    """升级武器。"""

    await send_reply(player_id, service.upgrade(player_id, message), manager, service)


@MessageHandler.handler(cmd="附魔武器", priority=100, block=True)
async def ws_weapon_enchant(message: str, player_id: str = Depends(current_player_id)) -> None:
    """附魔武器。"""

    await send_reply(player_id, service.enchant(player_id, message), manager, service)
