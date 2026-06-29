"""修仙帮助组件 命令。"""

from __future__ import annotations

from io import BytesIO

from launch import C, OnEvent, logger
from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import HELP_IMAGE, service
from .map_page import router as map_router
from .site import load_help_site, router


__all__ = ["router"]
router.include_router(map_router)


@OnEvent.connect(priority=40)
async def start_help_site() -> None:
    """服务启动时读取修仙 Markdown 文档并生成帮助站缓存。"""

    site = load_help_site()
    logger.opt(colors=True).info(
        f"{C.ok('执行 修仙帮助站 启动')} 文档 {len(site.docs)} 份，组件 {len(site.groups)} 个"
    )


@MessageHandler.handler(cmd="帮助", priority=100, block=True)
async def ws_web_help(player_id: str = Depends(current_player_id)) -> None:
    """发送帮助入口提示。"""

    await send_reply(
        player_id,
        service.web_help(),
        manager,
        service,
    )


@MessageHandler.handler(cmd="修仙帮助", priority=100, block=True)
async def ws_xiuxian_help_image(player_id: str = Depends(current_player_id)) -> None:
    """发送修仙帮助图。"""

    if not HELP_IMAGE.exists():
        await send_reply(
            player_id,
            {
                "code": 202,
                "type": "text",
                "message": "修仙帮助图不存在。\n发送：帮助 查看网页地址。",
                "auto_buttons": False,
                "default_buttons": False,
            },
            manager,
            service,
        )
        return

    image_bytes = HELP_IMAGE.read_bytes()
    image_io = BytesIO(image_bytes)
    await send_reply(
        player_id,
        {
            "code": 202,
            "type": "image",
            "message": image_io,
        },
        manager,
        service,
    )


@MessageHandler.handler(cmd="地图", priority=100, block=True)
async def ws_world_map(player_id: str = Depends(current_player_id)) -> None:
    """发送交互地图网页入口。"""

    await send_reply(
        player_id,
        service.map_help(player_id),
        manager,
        service,
    )


@MessageHandler.handler(cmd="指南", priority=100, block=True)
async def ws_command_guide(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看关键组件按钮导航。"""

    await send_reply(
        player_id,
        {
            "code": 202,
            "type": "text",
            "message": service.command_guide(message),
            "auto_buttons": False,
            "default_buttons": False,
        },
        manager,
        service,
    )


@MessageHandler.handler(cmd="引导", priority=100, block=True)
async def ws_daily_guide(player_id: str = Depends(current_player_id)) -> None:
    """查看日常入口无框命令链接。"""

    await send_reply(
        player_id,
        {
            "code": 202,
            "type": "text",
            "message": service.daily_guide(),
            "auto_buttons": False,
            "default_buttons": False,
        },
        manager,
        service,
    )
