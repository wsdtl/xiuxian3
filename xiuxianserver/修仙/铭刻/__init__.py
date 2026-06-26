"""铭刻组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="铭刻", priority=100, block=True)
async def ws_inscription_guide_or_dispatch(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看铭刻格式，或按目标分发铭刻。"""

    await send_reply(player_id, service.dispatch(player_id, message), manager, service)


@MessageHandler.handler(cmd="铭刻之羽", priority=100, block=True)
async def ws_inscription_feathers(player_id: str = Depends(current_player_id)) -> None:
    """查看未使用的铭刻之羽。"""

    await send_reply(player_id, service.feathers(player_id), manager, service)


@MessageHandler.handler(cmd="铭刻装备", priority=100, block=True)
async def ws_inscription_fixed_equipment(message: str, player_id: str = Depends(current_player_id)) -> None:
    """铭刻装备。"""

    await send_reply(player_id, service.fixed_equipment(player_id, message), manager, service)


@MessageHandler.handler(cmd="铭刻武器", priority=100, block=True)
async def ws_inscription_weapon(message: str, player_id: str = Depends(current_player_id)) -> None:
    """铭刻武器。"""

    await send_reply(player_id, service.weapon(player_id, message), manager, service)


@MessageHandler.handler(cmd="铭刻附魔", priority=100, block=True)
async def ws_inscription_enchant(message: str, player_id: str = Depends(current_player_id)) -> None:
    """铭刻武器上已附魔的技能书。"""

    await send_reply(player_id, service.enchant(player_id, message), manager, service)


@MessageHandler.handler(cmd="铭刻技能", priority=100, block=True)
async def ws_inscription_skill(message: str, player_id: str = Depends(current_player_id)) -> None:
    """铭刻武器自带技能；带附魔序号时仍可铭刻附魔。"""

    await send_reply(player_id, service.skill_or_enchant(player_id, message), manager, service)
