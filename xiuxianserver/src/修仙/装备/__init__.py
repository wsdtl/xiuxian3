"""固定装备组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd="固定装备", priority=100, block=True)
async def ws_equipment_list(client_id: str, message: str) -> None:
    """查看固定装备。"""

    await ws_manager.send(service.list_equipment(client_id), client_id)


@WsMessageHandler.handler(cmd=("固定装备升级", "升级固定装备"), priority=100, block=True)
async def ws_equipment_upgrade(client_id: str, message: str) -> None:
    """升级固定装备。"""

    await ws_manager.send(service.upgrade(client_id, message), client_id)


@WsMessageHandler.handler(cmd="孔位", priority=100, block=True)
async def ws_equipment_holes(client_id: str, message: str) -> None:
    """查看孔位。"""

    await ws_manager.send(service.holes(client_id, message), client_id)


@WsMessageHandler.handler(cmd="开孔", priority=100, block=True)
async def ws_equipment_open_hole(client_id: str, message: str) -> None:
    """固定装备开孔。"""

    await ws_manager.send(service.open_hole(client_id, message), client_id)


@WsMessageHandler.handler(cmd="镶嵌", priority=100, block=True)
async def ws_equipment_inlay(client_id: str, message: str) -> None:
    """镶嵌宝石。"""

    await ws_manager.send(service.inlay(client_id, message), client_id)


@WsMessageHandler.handler(cmd="拆卸", priority=100, block=True)
async def ws_equipment_remove_inlay(client_id: str, message: str) -> None:
    """拆卸宝石。"""

    await ws_manager.send(service.remove_inlay(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("宝石升级", "升级宝石"), priority=100, block=True)
async def ws_equipment_upgrade_inlay(client_id: str, message: str) -> None:
    """升级宝石。"""

    await ws_manager.send(service.upgrade_inlay(client_id, message), client_id)


@WsMessageHandler.handler(cmd="我的宝石", priority=100, block=True)
async def ws_equipment_my_inlays(client_id: str, message: str) -> None:
    """查看宝石。"""

    await ws_manager.send(service.my_inlays(client_id), client_id)
