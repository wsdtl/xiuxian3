"""消息流水组件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from launch import C, OnEvent, logger
from launch.adapter import MessageHandler, manager
from launch.paths import static_path
from launch.message_events import subscribe_message_events, unsubscribe_message_events

from ..constants import MESSAGE_FLOW_MAX_ROWS, MESSAGE_FLOW_RETENTION_DAYS
from ..reply import send_reply
from .service import FlowRecord, render_markdown_fragment, service


router = APIRouter(prefix="/xiuxian/message-flow")
INDEX_HTML = static_path("message-flow", "index.html")


@router.get("", response_class=HTMLResponse)
async def message_flow_page() -> str:
    """返回消息流水公开页面。"""

    return _render_page()


@router.get("/api/recent")
async def message_flow_recent(
    limit: int = 100,
) -> dict[str, Any]:
    """读取公开最近消息流水。"""

    records = await service.recent(limit=limit)
    return {"records": [_record_payload(record) for record in records]}


@router.get("/stream")
async def message_flow_stream(
    request: Request,
) -> StreamingResponse:
    """推送公开实时消息流水。"""

    queue = await service.subscribe()

    async def events():
        try:
            while not await request.is_disconnected():
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if record.flow_id <= 0:
                    break
                yield f"data: {json.dumps(_record_payload(record), ensure_ascii=False)}\n\n"
        finally:
            await service.unsubscribe(queue=queue)

    return StreamingResponse(events(), media_type="text/event-stream")


@MessageHandler.handler(cmd=("消息流水", "消息记录"), priority=100, block=True)
async def ws_message_flow(client_id: str) -> None:
    """查看消息流水公开入口。"""

    await send_reply(client_id, service.overview(), manager, service)


@OnEvent.connect(priority=41)
async def start_message_flow() -> None:
    """启动消息流水订阅。"""

    await service.start()
    subscribe_message_events(service.handle_event)
    logger.opt(colors=True).info(f"{C.ok('执行 消息流水 启动')}")


@OnEvent.disconnect(priority=41)
async def stop_message_flow() -> None:
    """停止消息流水订阅。"""

    unsubscribe_message_events(service.handle_event)
    await service.shutdown()
    logger.opt(colors=True).info(f"{C.warn('执行 消息流水 关闭')}")


def _record_payload(record: dict[str, Any] | FlowRecord) -> dict[str, Any]:
    data = record.to_dict() if isinstance(record, FlowRecord) else dict(record)
    if not str(data.get("sender_name") or "").strip():
        direction = str(data.get("direction") or "").strip()
        if direction == "outgoing":
            data["sender_name"] = "修仙服务"
        else:
            data["sender_name"] = str(data.get("display_name") or data.get("player_id") or data.get("client_id") or "未知道友")
    data["content_html"] = render_markdown_fragment(str(data.get("content") or ""))
    return data


def _render_page() -> str:
    """读取静态页面模板并注入当前会话配置。"""

    html = INDEX_HTML.read_text(encoding="utf-8")
    config = {
        "recentUrl": "/xiuxian/message-flow/api/recent?limit=160",
        "streamUrl": "/xiuxian/message-flow/stream",
        "visibleLimit": 200,
    }
    return html.replace("__MESSAGE_FLOW_CONFIG__", _json_for_script(config))


def _json_for_script(data: dict[str, Any]) -> str:
    """生成可安全放进 script 标签的 JSON。"""

    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


__all__ = ["router"]
