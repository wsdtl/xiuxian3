from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import config
from .log import C, logger
from .adapter import BaseAdapter, enabled_adapter_specs


async def FastAPIMount(app: "FastAPI") -> None:
    """挂载 FastAPI 全局资源。"""

    static_dir = config.base_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    if any(getattr(route, "path", "") == "/static" for route in app.routes):
        return

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


async def AdapterMount(app: "FastAPI") -> list[type[BaseAdapter]]:
    """挂载通信适配器，并返回需要启动/关闭的处理器。"""

    adapters: list[type[BaseAdapter]] = []

    for spec in enabled_adapter_specs():
        if not any(getattr(route, "path", "") == spec.route for route in app.routes):
            app.include_router(spec.router)
            logger.opt(colors=True).success(
                f"{C.ok('已挂载适配器')} {C.kv('name', spec.name)} {C.kv('path', spec.route)}"
            )

        adapters.append(spec.handler)

    return adapters
