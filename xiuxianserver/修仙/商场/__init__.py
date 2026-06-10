"""商场跑商组件 WS 命令。"""

from __future__ import annotations

from launch.adapter.ws import WsMessageHandler, manager as ws_manager

from ..reply import send_reply
from .service import service


@WsMessageHandler.handler(cmd=("商场"), priority=100, block=True)
async def ws_trade_current(client_id: str, message: str) -> None:
    """查看当前位置商场。"""

    await send_reply(client_id, service.current(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="商场列表", priority=100, block=True)
async def ws_trade_locations(client_id: str, message: str) -> None:
    """查看跑商地点。"""

    await send_reply(client_id, service.locations(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="商场详情", priority=100, block=True)
async def ws_trade_detail(client_id: str, message: str) -> None:
    """查看地点详情。"""

    await send_reply(client_id, service.detail(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="商场行情", priority=100, block=True)
async def ws_trade_price(client_id: str, message: str) -> None:
    """查看商品市价。"""

    await send_reply(client_id, service.market_price(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="商场购买", priority=100, block=True)
async def ws_trade_buy(client_id: str, message: str) -> None:
    """购买跑商商品。"""

    await send_reply(client_id, service.buy(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="商场出售", priority=100, block=True)
async def ws_trade_sell(client_id: str, message: str) -> None:
    """出售跑商商品。"""

    await send_reply(client_id, service.sell(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd="商场自动出售", priority=100, block=True)
async def ws_trade_auto_sell(client_id: str, message: str) -> None:
    """自动出售可跑商商品。"""

    await send_reply(client_id, service.auto_sell(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="商场推荐", priority=100, block=True)
async def ws_trade_recommend(client_id: str, message: str) -> None:
    """推荐跑商路线。"""

    await send_reply(client_id, service.recommend(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="跑商记录", priority=100, block=True)
async def ws_trade_records(client_id: str, message: str) -> None:
    """查看跑商记录。"""

    await send_reply(client_id, service.records(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="跑商限制", priority=100, block=True)
async def ws_trade_limits(client_id: str, message: str) -> None:
    """查看跑商限制。"""

    await send_reply(client_id, service.limits(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="跑商奖励", priority=100, block=True)
async def ws_trade_daily_reward(client_id: str, message: str) -> None:
    """领取每日跑商奖励。"""

    await send_reply(client_id, service.daily_reward(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="特殊收购", priority=100, block=True)
async def ws_special_buyers(client_id: str, message: str) -> None:
    """查看特殊收购。"""

    await send_reply(client_id, service.special_buyers(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd="特殊出售", priority=100, block=True)
async def ws_special_sell(client_id: str, message: str) -> None:
    """出售特殊收购物。"""

    await send_reply(client_id, service.special_sell(client_id, message), ws_manager, service)


@WsMessageHandler.handler(cmd=("特殊自动出售", "自动出售战利品"), priority=100, block=True)
async def ws_special_auto_sell(client_id: str, message: str) -> None:
    """自动出售所有特殊收购物。"""

    await send_reply(client_id, service.special_auto_sell(client_id), ws_manager, service)


@WsMessageHandler.handler(cmd=("导航", "去", "来"), priority=100, block=True)
async def ws_trade_navigate(client_id: str, message: str) -> None:
    """移动到指定地点。"""

    await send_reply(client_id, service.navigate(client_id, message), ws_manager, service)
