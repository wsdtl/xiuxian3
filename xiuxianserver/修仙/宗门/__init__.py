"""宗门组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from . import scheduler  # noqa: F401
from .service import service


@MessageHandler.handler(cmd="宗门", priority=100, block=True)
async def ws_sect_overview(player_id: str = Depends(current_player_id)) -> None:
    """查看宗门信息。"""

    await send_reply(player_id, service.overview(player_id), manager, service)


@MessageHandler.handler(cmd="宗门成员", priority=100, block=True)
async def ws_sect_members(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看宗门成员名册。"""

    await send_reply(player_id, service.members(player_id, message), manager, service)


@MessageHandler.handler(cmd="建立宗门", priority=100, block=True)
async def ws_create_sect(message: str, player_id: str = Depends(current_player_id)) -> None:
    """建立宗门。"""

    await send_reply(player_id, service.create(player_id, message), manager, service)


@MessageHandler.handler(cmd="加入宗门", priority=100, block=True)
async def ws_join_sect(message: str, player_id: str = Depends(current_player_id)) -> None:
    """加入当前位置宗门。"""

    await send_reply(player_id, service.join(player_id, message), manager, service)


@MessageHandler.handler(cmd="退出宗门", priority=100, block=True)
async def ws_quit_sect(player_id: str = Depends(current_player_id)) -> None:
    """退出当前宗门。"""

    await send_reply(player_id, service.quit(player_id), manager, service)


@MessageHandler.handler(cmd="宗门大会", priority=100, block=True)
async def ws_sect_war(player_id: str = Depends(current_player_id)) -> None:
    """查看宗门大会。"""

    await send_reply(player_id, service.war(player_id), manager, service)


@MessageHandler.handler(cmd="领取宗门大会奖励", priority=100, block=True)
async def ws_claim_sect_war_reward(player_id: str = Depends(current_player_id)) -> None:
    """领取宗门大会奖励。"""

    await send_reply(player_id, service.claim_war_reward(player_id), manager, service)
