"""玩家组件 WS 命令。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


HELP_IMAGE = Path(__file__).with_name("help.png")


@WsMessageHandler.handler(cmd="帮助", priority=100, block=True)
async def ws_xiuxian_guide(client_id: str, message: str) -> None:
    """查看新手指引。"""

    if not HELP_IMAGE.exists():
        await send_reply(client_id, service.guide(), ws_manager, service)
        return

    image_bytes = HELP_IMAGE.read_bytes()
    image_io = BytesIO(image_bytes)
    await send_reply(
        client_id,
        {
            "code": 202,
            "type": "image",
            "message": image_io,
        },
        ws_manager,
        service,
    )


@WsMessageHandler.handler(cmd=("创建用户", "用户创建"), priority=100, block=True)
async def ws_create_player(client_id: str, message: str) -> None:
    """创建修仙用户。"""

    await send_reply(client_id, service.create(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="改名", priority=100, block=True)
async def ws_rename_player(client_id: str, message: str) -> None:
    """修改展示名称。"""

    await send_reply(client_id, service.rename(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd=("修仙信息", "状态"), priority=100, block=True)
async def ws_profile(client_id: str, message: str) -> None:
    """查看玩家信息。"""

    await send_reply(client_id, service.profile(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="自动用药", priority=100, block=True)
async def ws_auto_medicine(client_id: str, message: str) -> None:
    """查看或修改探险自动用药开关。"""

    await send_reply(client_id, service.auto_medicine(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="签到", priority=100, block=True)
async def ws_sign(client_id: str, message: str) -> None:
    """每日签到。"""

    await send_reply(client_id, service.sign(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("新手礼包", "礼包"), priority=100, block=True)
async def ws_newbie_gift(client_id: str, message: str) -> None:
    """领取新手礼包。"""

    await send_reply(client_id, service.newbie_gift(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="休息", priority=100, block=True)
async def ws_rest(client_id: str, message: str) -> None:
    """进入休息状态。"""

    await send_reply(client_id, service.rest(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("结束休息", "休息结束"), priority=100, block=True)
async def ws_end_rest(client_id: str, message: str) -> None:
    """结束休息并恢复。"""

    await send_reply(client_id, service.end_rest(client_id), ws_manager, service)
