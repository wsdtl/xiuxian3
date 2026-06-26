"""纳戒组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="纳戒", priority=100, block=True)
async def ws_ring_list(player_id: str = Depends(current_player_id)) -> None:
    """查看纳戒。"""

    await send_reply(player_id, service.list_items(player_id), manager, service)


@MessageHandler.handler(cmd="体质重塑", priority=100, block=True)
async def ws_ring_remold_physique(player_id: str = Depends(current_player_id)) -> None:
    """消耗体质重塑道具刷新体质。"""

    await send_reply(player_id, service.remold_physique(player_id), manager, service)


@MessageHandler.handler(cmd="武器升限", priority=100, block=True)
async def ws_ring_raise_weapon_limit(message: str, player_id: str = Depends(current_player_id)) -> None:
    """消耗武器升限道具提升武器上限。"""

    await send_reply(player_id, service.raise_weapon_limit(player_id, message), manager, service)


@MessageHandler.handler(cmd="开孔", priority=100, block=True)
async def ws_ring_open_equipment_hole(message: str, player_id: str = Depends(current_player_id)) -> None:
    """消耗开孔器给装备开孔。"""

    await send_reply(player_id, service.open_equipment_hole(player_id, message), manager, service)
