"""修仙模块入口。

作为 APP_ROUTER_GROUPS 根模块时，这里暴露 router 并注册生命周期。
玩法包由 APP_ROUTER_GROUPS 加载器导入，并在各自包内注册 ws 触发器。
"""

from launch import C, OnEvent, logger

from .sql import db
from .url import router as router

__all__ = ["router"]


@OnEvent.connect()
async def start_db() -> None:
    """服务启动时准备修仙玩法数据库。"""

    db.init()
    logger.opt(colors=True).info(f"{C.ok('执行 修仙数据库 启动')}")


@OnEvent.disconnect()
async def stop_db() -> None:
    """服务关闭时释放修仙玩法数据库连接。"""

    db.close()
    logger.opt(colors=True).info(f"{C.warn('执行 修仙数据库 关闭')}")
