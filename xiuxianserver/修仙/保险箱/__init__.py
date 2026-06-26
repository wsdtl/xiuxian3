"""保险箱组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd=("保险箱", "查看保险箱"), priority=100, block=True)
async def ws_vault_list(player_id: str = Depends(current_player_id)) -> None:
    """查看保险箱。"""

    await send_reply(player_id, service.list_items(player_id), manager, service)


@MessageHandler.handler(cmd=("存入保险箱", "存保险箱", "放入保险箱"), priority=100, block=True)
async def ws_vault_deposit(message: str, player_id: str = Depends(current_player_id)) -> None:
    """存入保险箱。"""

    await send_reply(player_id, service.deposit(player_id, message), manager, service)


@MessageHandler.handler(cmd=("取出保险箱", "取保险箱"), priority=100, block=True)
async def ws_vault_withdraw(message: str, player_id: str = Depends(current_player_id)) -> None:
    """从保险箱取出。"""

    await send_reply(player_id, service.withdraw(player_id, message), manager, service)
