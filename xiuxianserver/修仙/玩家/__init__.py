"""玩家组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id
from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="创建用户", priority=100, block=True)
async def ws_create_player(client_id: str, message: str) -> None:
    """创建修仙用户。"""

    await send_reply(client_id, service.create(client_id, message), manager, service)


@MessageHandler.handler(cmd="改名", priority=100, block=True)
async def ws_rename_player(message: str, player_id: str = Depends(current_player_id)) -> None:
    """修改展示名称。"""

    await send_reply(player_id, service.rename(player_id, message), manager, service)


@MessageHandler.handler(cmd="修仙信息", priority=100, block=True)
async def ws_profile(player_id: str = Depends(current_player_id)) -> None:
    """查看玩家详细信息。"""

    await send_reply(player_id, service.profile(player_id), manager, service)


@MessageHandler.handler(cmd="状态", priority=100, block=True)
async def ws_status(player_id: str = Depends(current_player_id)) -> None:
    """查看玩家关键状态。"""

    await send_reply(player_id, service.status(player_id), manager, service)


@MessageHandler.handler(cmd="修仙日记", priority=100, block=True)
async def ws_player_diary(player_id: str = Depends(current_player_id)) -> None:
    """查看个人修仙日记。"""

    await send_reply(player_id, service.diary(player_id), manager, service)


@MessageHandler.handler(cmd="自动用药", priority=100, block=True)
async def ws_auto_medicine(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看或修改探险自动用药开关。"""

    await send_reply(player_id, service.auto_medicine(player_id, message), manager, service)


@MessageHandler.handler(cmd="战斗日志", priority=100, block=True)
async def ws_battle_log(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看或修改战斗日志展示模式。"""

    await send_reply(player_id, service.battle_log(player_id, message), manager, service)


@MessageHandler.handler(cmd="签到", priority=100, block=True)
async def ws_sign(player_id: str = Depends(current_player_id)) -> None:
    """每日签到。"""

    await send_reply(player_id, service.sign(player_id), manager, service)


@MessageHandler.handler(cmd="新手礼包", priority=100, block=True)
async def ws_newbie_gift(player_id: str = Depends(current_player_id)) -> None:
    """领取新手礼包。"""

    await send_reply(player_id, service.newbie_gift(player_id), manager, service)


@MessageHandler.handler(cmd="休息", priority=100, block=True)
async def ws_rest(player_id: str = Depends(current_player_id)) -> None:
    """进入休息状态。"""

    await send_reply(player_id, service.rest(player_id), manager, service)


@MessageHandler.handler(cmd=("结束休息", "休息结束"), priority=100, block=True)
async def ws_end_rest(player_id: str = Depends(current_player_id)) -> None:
    """结束休息并恢复。"""

    await send_reply(player_id, service.end_rest(player_id), manager, service)
