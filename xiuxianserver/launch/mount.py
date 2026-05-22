from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .log import C, logger


async def FastAPIMount(app: "FastAPI") -> None:
    """挂载 FastAPI 全局资源。"""

    app.mount("/static", StaticFiles(directory="static"), name="static")


async def AdapterMount(app: "FastAPI") -> list:
    """挂载通信适配器，并返回需要启动/关闭的处理器。"""

    _adapter = []

    from .adapter import ws

    app.include_router(ws.router)
    logger.opt(colors=True).success(
        f"{C.ok('Loaded handler')} {C.kv('path', ws.WS_ROUTE)}"
    )
    _adapter.append(ws.WsMessageHandler)

    return _adapter
