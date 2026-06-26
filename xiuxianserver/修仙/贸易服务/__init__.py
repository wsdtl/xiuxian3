"""贸易服务交易、出售和导航 命令。"""

from __future__ import annotations

from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id

from ..reply import send_reply
from .service import service


@MessageHandler.handler(cmd="商场行情", priority=100, block=True)
async def ws_trade_price(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看商品市价。"""

    await send_reply(player_id, service.market_price(player_id, message), manager, service)


@MessageHandler.handler(cmd="商场购买", priority=100, block=True)
async def ws_trade_buy(message: str, player_id: str = Depends(current_player_id)) -> None:
    """购买跑商商品。"""

    await send_reply(player_id, service.buy(player_id, message), manager, service)


@MessageHandler.handler(cmd="商场出售", priority=100, block=True)
async def ws_trade_sell(message: str, player_id: str = Depends(current_player_id)) -> None:
    """出售跑商商品。"""

    await send_reply(player_id, service.sell(player_id, message), manager, service)


@MessageHandler.handler(cmd="出售", priority=100, block=True)
async def ws_sell_any(message: str, player_id: str = Depends(current_player_id)) -> None:
    """统一出售指定物品。"""

    await send_reply(player_id, service.sell_any(player_id, message), manager, service)


@MessageHandler.handler(cmd="自动出售", priority=100, block=True)
async def ws_auto_sell(player_id: str = Depends(current_player_id)) -> None:
    """自动清空背包可流通物品。"""

    await send_reply(player_id, service.auto_sell(player_id), manager, service)


@MessageHandler.handler(cmd="出售全部", priority=100, block=True)
async def ws_sell_all(message: str, player_id: str = Depends(current_player_id)) -> None:
    """批量出售纳戒资产。"""

    await send_reply(player_id, service.sell_all(player_id, message), manager, service)


@MessageHandler.handler(cmd="藏宝图", priority=100, block=True)
async def ws_treasure_map(message: str, player_id: str = Depends(current_player_id)) -> None:
    """查看当前位置或指定城池藏宝图。"""

    await send_reply(player_id, service.treasure_map(player_id, message), manager, service)


@MessageHandler.handler(cmd="藏宝图出价", priority=100, block=True)
async def ws_treasure_bid(message: str, player_id: str = Depends(current_player_id)) -> None:
    """给当前位置城池藏宝图出价。"""

    await send_reply(player_id, service.treasure_bid(player_id, message), manager, service)


@MessageHandler.handler(cmd="领取藏宝图", priority=100, block=True)
async def ws_treasure_claim(player_id: str = Depends(current_player_id)) -> None:
    """领取已归属或脚下的藏宝图。"""

    await send_reply(player_id, service.treasure_claim(player_id), manager, service)


@MessageHandler.handler(cmd="商场推荐", priority=100, block=True)
async def ws_trade_recommend(player_id: str = Depends(current_player_id)) -> None:
    """推荐跑商路线。"""

    await send_reply(player_id, service.recommend(player_id), manager, service)


@MessageHandler.handler(cmd="跑商记录", priority=100, block=True)
async def ws_trade_records(player_id: str = Depends(current_player_id)) -> None:
    """查看跑商记录。"""

    await send_reply(player_id, service.records(player_id), manager, service)


@MessageHandler.handler(cmd="跑商限制", priority=100, block=True)
async def ws_trade_curve(player_id: str = Depends(current_player_id)) -> None:
    """查看跑商收益曲线。"""

    await send_reply(player_id, service.trade_curve(player_id), manager, service)


@MessageHandler.handler(cmd="跑商奖励", priority=100, block=True)
async def ws_trade_daily_reward(player_id: str = Depends(current_player_id)) -> None:
    """领取每日跑商奖励。"""

    await send_reply(player_id, service.daily_reward(player_id), manager, service)


@MessageHandler.handler(cmd=("导航", "去", "来"), priority=100, block=True)
async def ws_trade_navigate(message: str, player_id: str = Depends(current_player_id)) -> None:
    """移动到指定地点。"""

    await send_reply(player_id, service.navigate(player_id, message), manager, service)
