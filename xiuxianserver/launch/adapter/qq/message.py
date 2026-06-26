"""QQ webhook HTTP 入口。

本文件只负责 FastAPI 路由层：读取 JSON、处理开放平台地址验证、
把普通事件交给 handler。真正的命令调度不在 HTTP 入口里完成。
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from launch.log import C, logger
from launch.config import config

from .handler import QqEventHandler


QQ_EVENT_ROUTE = config.get("QQ_EVENT_PATH", "/qq/events") or "/qq/events"
router = APIRouter()


@router.post(QQ_EVENT_ROUTE)
async def qq_event_endpoint(request: Request) -> Dict[str, Any]:
    """接收 QQ 开放平台事件回调。

    op=13 是开放平台的回调地址验证，必须同步返回签名结果。
    其他 payload 统一交给 QqEventHandler，handler 会快速 ACK 并把消息
    事件放进后台任务队列。
    """

    payload = await _read_payload(request)
    op = payload.get("op")

    if op == 13:
        try:
            response = await QqEventHandler.validation(payload)
        except ValueError as exc:
            logger.opt(colors=True).warning(
                f"{C.warn('QQ 回调验证失败')} {C.kv('reason', exc)}"
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        logger.opt(colors=True).success(f"{C.ok('QQ 回调验证已响应')}")
        return response

    return await QqEventHandler.dispatch(payload=payload)


async def _read_payload(request: Request) -> Dict[str, Any]:
    """读取并校验 QQ webhook JSON。"""

    try:
        payload = await request.json()
    except Exception as exc:
        logger.opt(colors=True, exception=exc).warning(f"{C.warn('QQ 回调 JSON 无效')}")
        raise HTTPException(status_code=400, detail="JSON 无效") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="QQ 回调内容必须是对象")
    return payload
