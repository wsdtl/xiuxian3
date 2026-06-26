"""用户组绑定命令和后台路由。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id
from .router import router
from .service import service


@MessageHandler.handler(cmd=("用户组", "用户组后台"), priority=100, block=True)
async def ws_user_group_overview(client_id: str) -> None:
    """查看用户组后台地址和绑定流程。"""

    await manager.send(service.overview(), client_id)


@MessageHandler.handler(cmd="用户组后台登录", priority=100, block=True)
async def ws_user_group_admin_login(
    client_id: str,
    message: str,
    player_id: str = Depends(current_player_id),
) -> None:
    """用已有角色确认用户组后台登录码。"""

    await manager.send(service.confirm_admin_login(player_id, message), client_id)


@MessageHandler.handler(cmd="绑定用户组", priority=100, block=True)
async def ws_bind_user_group(client_id: str, message: str) -> None:
    """把当前入口绑定到后台生成绑定码对应的用户组。"""

    await manager.send(service.bind_user_group(client_id, message), client_id)


__all__ = ["router"]
