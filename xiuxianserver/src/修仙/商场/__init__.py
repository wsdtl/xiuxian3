"""商场跑商组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from .service import service


@WsMessageHandler.handler(cmd="商场", priority=100, block=True)
async def ws_trade_current(client_id: str, message: str) -> None:
    """查看当前位置商场。"""

    await ws_manager.send(service.current(client_id), client_id)


@WsMessageHandler.handler(cmd=("商场列表", "列表商场"), priority=100, block=True)
async def ws_trade_locations(client_id: str, message: str) -> None:
    """查看跑商地点。"""

    await ws_manager.send(service.locations(client_id), client_id)


@WsMessageHandler.handler(cmd=("商场详情", "详情商场"), priority=100, block=True)
async def ws_trade_detail(client_id: str, message: str) -> None:
    """查看地点详情。"""

    await ws_manager.send(service.detail(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("商场市价", "市价商场"), priority=100, block=True)
async def ws_trade_price(client_id: str, message: str) -> None:
    """查看商品市价。"""

    await ws_manager.send(service.market_price(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("商场购买", "购买商场"), priority=100, block=True)
async def ws_trade_buy(client_id: str, message: str) -> None:
    """购买跑商商品。"""

    await ws_manager.send(service.buy(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("商场出售", "出售商场"), priority=100, block=True)
async def ws_trade_sell(client_id: str, message: str) -> None:
    """出售跑商商品。"""

    await ws_manager.send(service.sell(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("商场自动出售", "自动出售商场"), priority=100, block=True)
async def ws_trade_auto_sell(client_id: str, message: str) -> None:
    """自动出售可跑商商品。"""

    await ws_manager.send(service.auto_sell(client_id), client_id)


@WsMessageHandler.handler(cmd=("商场推荐", "推荐商场"), priority=100, block=True)
async def ws_trade_recommend(client_id: str, message: str) -> None:
    """推荐跑商路线。"""

    await ws_manager.send(service.recommend(client_id), client_id)


@WsMessageHandler.handler(cmd=("商场记录", "记录商场"), priority=100, block=True)
async def ws_trade_records(client_id: str, message: str) -> None:
    """查看跑商记录。"""

    await ws_manager.send(service.records(client_id), client_id)


@WsMessageHandler.handler(cmd=("商场限制", "限制商场"), priority=100, block=True)
async def ws_trade_limits(client_id: str, message: str) -> None:
    """查看跑商限制。"""

    await ws_manager.send(service.limits(client_id), client_id)


@WsMessageHandler.handler(cmd=("特殊收购", "收购特殊"), priority=100, block=True)
async def ws_special_buyers(client_id: str, message: str) -> None:
    """查看特殊收购。"""

    await ws_manager.send(service.special_buyers(client_id), client_id)


@WsMessageHandler.handler(cmd=("特殊出售", "出售特殊"), priority=100, block=True)
async def ws_special_sell(client_id: str, message: str) -> None:
    """出售特殊收购物。"""

    await ws_manager.send(service.special_sell(client_id, message), client_id)


@WsMessageHandler.handler(cmd=("特殊自动出售", "自动出售特殊"), priority=100, block=True)
async def ws_special_auto_sell(client_id: str, message: str) -> None:
    """自动出售所有特殊收购物。"""

    await ws_manager.send(service.special_auto_sell(client_id), client_id)


@WsMessageHandler.handler(cmd="导航", priority=100, block=True)
async def ws_trade_navigate(client_id: str, message: str) -> None:
    """移动到指定地点。"""

    await ws_manager.send(service.navigate(client_id, message), client_id)
