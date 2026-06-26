"""装备组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="装备", priority=100, block=True)
async def ws_equipment_list(player_id: str = Depends(current_player_id)) -> None:
    """查看装备。"""

    await send_reply(player_id, service.list_equipment(player_id), manager, service)


@MessageHandler.handler(cmd=("装备升级", "升"), priority=100, block=True)
async def ws_equipment_upgrade(message: str, player_id: str = Depends(current_player_id)) -> None:
    """升级装备。"""

    await send_reply(player_id, service.upgrade(player_id, message), manager, service)


@MessageHandler.handler(cmd="孔位", priority=100, block=True)
async def ws_equipment_holes(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看孔位。"""

    await send_reply(player_id, service.holes(player_id, message), manager, service)


@MessageHandler.handler(cmd="镶嵌", priority=100, block=True)
async def ws_equipment_inlay(message: str, player_id: str = Depends(current_player_id)) -> None:
    """镶嵌宝石。"""

    await send_reply(player_id, service.inlay(player_id, message), manager, service)


@MessageHandler.handler(cmd="拆卸", priority=100, block=True)
async def ws_equipment_remove_inlay(message: str, player_id: str = Depends(current_player_id)) -> None:
    """拆卸宝石。"""

    await send_reply(player_id, service.remove_inlay(player_id, message), manager, service)


@MessageHandler.handler(cmd="宝石升级", priority=100, block=True)
async def ws_equipment_upgrade_inlay(message: str, player_id: str = Depends(current_player_id)) -> None:
    """升级宝石。"""

    await send_reply(player_id, service.upgrade_inlay(player_id, message), manager, service)


@MessageHandler.handler(cmd="宝石", priority=100, block=True)
async def ws_equipment_my_inlays(player_id: str = Depends(current_player_id)) -> None:
    """查看宝石。"""

    await send_reply(player_id, service.my_inlays(player_id), manager, service)
