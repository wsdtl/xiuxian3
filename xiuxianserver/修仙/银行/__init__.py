"""银行组件 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..common import to_int
from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="银行", priority=100, block=True)
async def ws_bank_info(player_id: str = Depends(current_player_id)) -> None:
    """查看银行。"""

    await send_reply(player_id, service.info(player_id), manager, service)


@MessageHandler.handler(cmd="银行结息", priority=100, block=True)
async def ws_bank_settle(player_id: str = Depends(current_player_id)) -> None:
    """银行结息。"""

    await send_reply(player_id, service.settle(player_id), manager, service)


@MessageHandler.handler(cmd=("银行升级", "升级银行"), priority=100, block=True)
async def ws_bank_upgrade(player_id: str = Depends(current_player_id)) -> None:
    """升级银行。"""

    await send_reply(player_id, service.upgrade(player_id), manager, service)


@MessageHandler.handler(cmd=("货币存入", "存入货币"), priority=100, block=True)
async def ws_bank_deposit(message: str, player_id: str = Depends(current_player_id)) -> None:
    """存入货币。"""

    await send_reply(player_id, service.deposit(player_id, to_int(message)), manager, service)


@MessageHandler.handler(cmd=("货币取出", "取出货币"), priority=100, block=True)
async def ws_bank_withdraw(message: str, player_id: str = Depends(current_player_id)) -> None:
    """取出货币。"""

    await send_reply(player_id, service.withdraw(player_id, to_int(message)), manager, service)
