"""修仙界历史 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="风云榜", priority=100, block=True)
async def ws_history_leaderboard(player_id: str = Depends(current_player_id)) -> None:
    """查看风云榜。"""

    await send_reply(player_id, service.leaderboard(player_id), manager, service)


@MessageHandler.handler(cmd="修仙早报", priority=100, block=True)
async def ws_history_morning_paper(player_id: str = Depends(current_player_id)) -> None:
    """查看今日修仙早报。"""

    await send_reply(player_id, service.newspaper(player_id), manager, service)


@MessageHandler.handler(cmd="修仙界历史", priority=100, block=True)
async def ws_history_chronicle(player_id: str = Depends(current_player_id)) -> None:
    """查看最近修仙界历史。"""

    await send_reply(player_id, service.chronicle(player_id), manager, service)


@MessageHandler.handler(cmd="人物史榜", priority=100, block=True)
async def ws_history_player_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看人物史榜。"""

    await send_reply(player_id, service.history_volume(player_id, "人物史榜"), manager, service)


@MessageHandler.handler(cmd="宗门史榜", priority=100, block=True)
async def ws_history_sect_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看宗门史榜。"""

    await send_reply(player_id, service.history_volume(player_id, "宗门史榜"), manager, service)


@MessageHandler.handler(cmd="城池史榜", priority=100, block=True)
async def ws_history_city_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看城池史榜。"""

    await send_reply(player_id, service.history_volume(player_id, "城池史榜"), manager, service)


@MessageHandler.handler(cmd="战斗名局", priority=100, block=True)
async def ws_history_battle_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看战斗名局。"""

    await send_reply(player_id, service.history_volume(player_id, "战斗名局"), manager, service)


@MessageHandler.handler(cmd="商路奇闻", priority=100, block=True)
async def ws_history_trade_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看商路奇闻。"""

    await send_reply(player_id, service.history_volume(player_id, "商路奇闻"), manager, service)


@MessageHandler.handler(cmd="异界虫洞录", priority=100, block=True)
async def ws_history_wormhole_volume(player_id: str = Depends(current_player_id)) -> None:
    """查看异界虫洞录。"""

    await send_reply(player_id, service.history_volume(player_id, "异界虫洞录"), manager, service)


@MessageHandler.handler(cmd="人物志", priority=100, block=True)
async def ws_history_profile(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看公开人物志。"""

    await send_reply(player_id, service.profile(player_id, message), manager, service)
