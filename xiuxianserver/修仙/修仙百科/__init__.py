"""修仙百科组件 命令。"""

from __future__ import annotations

from launch import C, OnEvent, logger
from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@OnEvent.connect(priority=40)
async def start_encyclopedia() -> None:
    """服务启动时缓存修仙百科知识。"""

    entries = service.load()
    logger.opt(colors=True).info(f"{C.ok('执行 修仙百科 启动')} 知识 {len(entries)} 条")


@MessageHandler.handler(cmd="修仙百科", priority=100, block=True)
async def ws_xiuxian_encyclopedia(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查询修仙百科。"""

    await send_reply(player_id, service.ask(player_id, message), manager, service)
