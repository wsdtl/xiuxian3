from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from launch import C, OnEvent, logger


@OnEvent.connect()
async def _():
    logger.opt(colors=True).info(f"{C.warn('执行 FastAPICache 初始化')}")
    FastAPICache.init(InMemoryBackend())
