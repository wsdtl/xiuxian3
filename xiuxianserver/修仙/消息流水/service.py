"""消息流水服务。"""

from __future__ import annotations

import asyncio
import html
import json
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Deque

from launch.message_events import MessageEvent

from ..constants import (
    MESSAGE_FLOW_GLOBAL_BUFFER,
    MESSAGE_FLOW_MAX_ROWS,
    MESSAGE_FLOW_PER_PLAYER_BUFFER,
    MESSAGE_FLOW_RETENTION_DAYS,
)
from ..identity import resolve_player_id
from ..markdown_utils import markdown_link
from ..public_url import public_url
from ..sql import db


MAX_CONTENT_LENGTH = 6000
MESSAGE_FLOW_PATH = "/xiuxian/message-flow"
HEADER_LINE_RE = re.compile(r"^【[^】]{0,80}】$")
SYSTEM_LINE_RE = re.compile(r"^(?:🔴\s*)?系统：")
NOTICE_LINE_RE = re.compile(r"^(?:🔴\s*)?通知：")


@dataclass(frozen=True)
class FlowRecord:
    """页面和 SSE 使用的消息流水记录。"""

    flow_id: int
    direction: str
    adapter: str
    request_id: str
    client_id: str
    player_id: str
    sender_name: str
    message_type: str
    content: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MessageFlowService:
    """消息流水核心服务。"""

    def __init__(self, database: Any | None = None) -> None:
        self.db = database if database is not None else db
        self._lock = asyncio.Lock()
        self._global_records: Deque[FlowRecord] = deque(maxlen=MESSAGE_FLOW_GLOBAL_BUFFER)
        self._player_records: dict[str, Deque[FlowRecord]] = defaultdict(
            lambda: deque(maxlen=MESSAGE_FLOW_PER_PLAYER_BUFFER)
        )
        self._subscribers: dict[str, set[asyncio.Queue[FlowRecord]]] = defaultdict(set)
        self._last_flow_id = 0

    def overview(self) -> str:
        """返回消息流水后台入口。"""

        return (
            f"消息流水页面：{message_flow_link()}\n"
            "所有人都可以直接打开查看最近消息流水。"
        )

    async def start(self) -> None:
        """从短期表恢复最新流水，供热重启后页面回放。"""

        self._last_flow_id = self._read_last_flow_id()
        for row in self._recent_rows_from_db(limit=MESSAGE_FLOW_GLOBAL_BUFFER):
            record = _record_from_row(row)
            self._remember_record(record)

    async def shutdown(self) -> None:
        """关闭所有 SSE 等待队列。"""

        async with self._lock:
            subscribers = [queue for queues in self._subscribers.values() for queue in queues]
            self._subscribers.clear()
        for queue in subscribers:
            queue.put_nowait(_closed_record())

    async def handle_event(self, event: MessageEvent) -> None:
        """接收驱动器事件，过滤后写入内存和短期表。"""

        record = await self.record_event(event)
        if record is None:
            return
        await self._publish(record)

    async def record_event(self, event: MessageEvent) -> FlowRecord | None:
        """把驱动器事件转换成消息流水记录。"""

        content = sanitize_event_content(event)
        if not content:
            return None

        player_id = resolve_player_id(event.client_id, self.db)
        record = await self._make_record(event, player_id, content)
        self._insert_record(record)
        await self._remember_record_locked(record)
        return record

    async def recent(self, player_id: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
        """读取最近消息；默认返回全局公开流水。"""

        normalized = str(player_id or "").strip()
        count = max(1, min(int(limit or 100), MESSAGE_FLOW_PER_PLAYER_BUFFER))
        async with self._lock:
            cached = list(self._global_records if not normalized else self._player_records.get(normalized, ()))
        if cached:
            return [record.to_dict() for record in cached[-count:]]

        rows = self._recent_rows_from_db(limit=count, player_id=normalized)
        return [dict(row) for row in rows]

    async def subscribe(self, player_id: str = "") -> asyncio.Queue[FlowRecord]:
        """订阅实时流水；默认订阅全局公开流。"""

        normalized = str(player_id or "").strip()
        queue: asyncio.Queue[FlowRecord] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[normalized].add(queue)
        return queue

    async def unsubscribe(
        self,
        player_id: str = "",
        queue: asyncio.Queue[FlowRecord] | None = None,
    ) -> None:
        """取消实时流水订阅。"""

        normalized = str(player_id or "").strip()
        if queue is None:
            return
        async with self._lock:
            queues = self._subscribers.get(normalized)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(normalized, None)

    def cleanup(self) -> None:
        """清理短期表，按 2 天和 5000 条双限制收口。"""

        cutoff = (datetime.now() - timedelta(days=MESSAGE_FLOW_RETENTION_DAYS)).isoformat(timespec="seconds")
        with self.db.transaction() as conn:
            conn.execute(
                """
                DELETE FROM message_flows
                WHERE datetime(replace(created_at, 'T', ' ')) < datetime(replace(?, 'T', ' '))
                """,
                (cutoff,),
            )
            conn.execute(
                """
                DELETE FROM message_flows
                WHERE flow_id NOT IN (
                    SELECT flow_id
                    FROM message_flows
                    ORDER BY flow_id DESC
                    LIMIT ?
                )
                """,
                (MESSAGE_FLOW_MAX_ROWS,),
            )

    async def _make_record(self, event: MessageEvent, player_id: str, content: str) -> FlowRecord:
        async with self._lock:
            self._last_flow_id = max(self._last_flow_id, self._read_last_flow_id()) + 1
            flow_id = self._last_flow_id
        direction = _safe_choice(event.direction, {"incoming", "outgoing"}, "incoming")
        resolved_player_id = _short_token(player_id or event.client_id)
        return FlowRecord(
            flow_id=flow_id,
            direction=direction,
            adapter=_short_token(event.adapter, "unknown"),
            request_id=_short_token(event.request_id),
            client_id=_short_token(event.client_id),
            player_id=resolved_player_id,
            sender_name=self._sender_name_for(direction, resolved_player_id, event.client_id),
            message_type=_safe_choice(event.message_type, {"text", "markdown", "image", "raw", "unknown"}, "unknown"),
            content=_truncate_content(content),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def _insert_record(self, record: FlowRecord) -> None:
        self.db.execute(
            """
            INSERT INTO message_flows (
                flow_id, direction, adapter, request_id, client_id, player_id,
                message_type, content, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.flow_id,
                record.direction,
                record.adapter,
                record.request_id,
                record.client_id,
                record.player_id,
                record.message_type,
                record.content,
                record.created_at,
            ),
        )
        if record.flow_id % 100 == 0:
            self.cleanup()

    async def _remember_record_locked(self, record: FlowRecord) -> None:
        async with self._lock:
            self._remember_record(record)

    def _remember_record(self, record: FlowRecord) -> None:
        self._global_records.append(record)
        self._player_records[record.player_id].append(record)

    async def _publish(self, record: FlowRecord) -> None:
        async with self._lock:
            queues = set(self._subscribers.get("", ()))
            queues.update(self._subscribers.get(record.player_id, ()))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(record)

    def _read_last_flow_id(self) -> int:
        try:
            row = self.db.fetch_one("SELECT COALESCE(MAX(flow_id), 0) AS last_id FROM message_flows")
        except Exception:
            return self._last_flow_id
        return int(row.get("last_id") or 0) if row else 0

    def _recent_rows_from_db(self, *, limit: int, player_id: str = "") -> list[dict[str, Any]]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT
                    mf.*,
                    CASE
                        WHEN mf.direction = 'outgoing' THEN '修仙服务'
                        ELSE COALESCE(p.display_name, mf.player_id, mf.client_id, '未知道友')
                    END AS sender_name
                FROM message_flows AS mf
                LEFT JOIN players AS p ON p.client_id = mf.player_id
                WHERE ? = '' OR mf.player_id = ?
                ORDER BY mf.flow_id DESC
                LIMIT ?
                """,
                (str(player_id or "").strip(), str(player_id or "").strip(), max(1, int(limit))),
            )
        except Exception:
            return []
        return list(reversed(rows))

    def _sender_name_for(self, direction: str, player_id: str, client_id: str) -> str:
        if direction == "outgoing":
            return "修仙服务"

        for token in (player_id, client_id):
            normalized = str(token or "").strip()
            if not normalized:
                continue
            try:
                row = self.db.fetch_one(
                    "SELECT display_name FROM players WHERE client_id = ? LIMIT 1",
                    (normalized,),
                )
            except Exception:
                continue
            name = str(row.get("display_name") or "").strip() if row else ""
            if name:
                return name

        fallback = str(player_id or client_id or "").strip()
        return fallback or "未知道友"


def sanitize_event_content(event: MessageEvent) -> str:
    """整理消息展示正文。"""

    text = str(event.content or "").strip()
    if not text:
        return ""
    if event.direction == "outgoing":
        text = _strip_reply_prefix_lines(text)
    return _truncate_content(text)


def render_markdown_fragment(text: str) -> str:
    """把项目内常用 Markdown 子集渲染成安全 HTML 片段。"""

    lines = str(text or "").splitlines()
    rendered: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                rendered.append(f"<pre><code>{html.escape(chr(10).join(code_lines), quote=False)}</code></pre>")
                code_lines = []
                in_code = False
            else:
                list_type = _close_markdown_list(rendered, list_type)
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            list_type = _close_markdown_list(rendered, list_type)
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            list_type = _close_markdown_list(rendered, list_type)
            level = len(heading.group(1))
            rendered.append(f"<h{level}>{_inline_markdown(heading.group(2).strip())}</h{level}>")
            continue

        if stripped in {"---", "***", "___"}:
            list_type = _close_markdown_list(rendered, list_type)
            rendered.append("<hr>")
            continue

        if line.lstrip().startswith(">"):
            list_type = _close_markdown_list(rendered, list_type)
            content = line.lstrip()[1:].strip()
            rendered.append(f"<blockquote><p>{_inline_markdown(content)}</p></blockquote>")
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            if list_type == "ol":
                rendered.append("</ol>")
                list_type = None
            if list_type != "ul":
                rendered.append("<ul>")
                list_type = "ul"
            rendered.append(f"<li>{_inline_markdown(bullet.group(1).strip())}</li>")
            continue

        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ordered:
            if list_type == "ul":
                rendered.append("</ul>")
                list_type = None
            if list_type != "ol":
                rendered.append("<ol>")
                list_type = "ol"
            rendered.append(f"<li>{_inline_markdown(ordered.group(1).strip())}</li>")
            continue

        list_type = _close_markdown_list(rendered, list_type)
        rendered.append(f"<p>{_inline_markdown(stripped)}</p>")

    if in_code:
        rendered.append(f"<pre><code>{html.escape(chr(10).join(code_lines), quote=False)}</code></pre>")
    _close_markdown_list(rendered, list_type)
    return "\n".join(rendered)


def message_flow_url() -> str:
    """返回消息流水后台公开地址。"""

    return public_url(MESSAGE_FLOW_PATH)


def message_flow_link(label: str = "消息流水后台") -> str:
    """返回隐藏真实地址的消息流水后台链接。"""

    return markdown_link(label, message_flow_url())


def _strip_reply_prefix_lines(text: str) -> str:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        value = lines[index].strip()
        if not value:
            index += 1
            continue
        if HEADER_LINE_RE.match(value) or SYSTEM_LINE_RE.match(value) or NOTICE_LINE_RE.match(value):
            index += 1
            continue
        break
    return "\n".join(lines[index:]).strip()


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped, code_spans = _extract_inline_code_spans(escaped)
    escaped = _render_images(escaped)
    escaped = _render_links(escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", escaped)
    return _restore_inline_code_spans(escaped, code_spans)


def _render_links(text: str) -> str:
    return re.sub(
        r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)",
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{match.group(1)}</a>'
        ),
        text,
    )


def _render_images(text: str) -> str:
    return re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        lambda match: (
            f'<img src="{html.escape(match.group(2), quote=True)}" '
            f'alt="{html.escape(match.group(1), quote=True)}" loading="lazy">'
        ),
        text,
    )


def _extract_inline_code_spans(text: str) -> tuple[str, dict[str, str]]:
    spans: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        placeholder = f"__CODE_SPAN_{len(spans)}__"
        spans[placeholder] = f"<code>{html.escape(match.group(1), quote=False)}</code>"
        return placeholder

    return re.sub(r"`([^`]+)`", replace, text), spans


def _restore_inline_code_spans(text: str, spans: dict[str, str]) -> str:
    for placeholder, code_html in spans.items():
        text = text.replace(placeholder, code_html)
    return text


def _close_markdown_list(rendered: list[str], list_type: str | None) -> str | None:
    if list_type == "ul":
        rendered.append("</ul>")
    elif list_type == "ol":
        rendered.append("</ol>")
    return None


def _record_from_row(row: dict[str, Any]) -> FlowRecord:
    return FlowRecord(
        flow_id=int(row.get("flow_id") or 0),
        direction=str(row.get("direction") or ""),
        adapter=str(row.get("adapter") or ""),
        request_id=str(row.get("request_id") or ""),
        client_id=str(row.get("client_id") or ""),
        player_id=str(row.get("player_id") or ""),
        sender_name=str(row.get("sender_name") or ""),
        message_type=str(row.get("message_type") or "unknown"),
        content=str(row.get("content") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _closed_record() -> FlowRecord:
    return FlowRecord(0, "system", "", "", "", "", "系统", "text", "", "")


def _safe_choice(value: object, choices: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in choices else default


def _short_token(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return text[:160]


def _truncate_content(text: str) -> str:
    value = str(text or "").strip()
    if len(value) <= MAX_CONTENT_LENGTH:
        return value
    return f"{value[:MAX_CONTENT_LENGTH]}..."


def sse_data(record: FlowRecord) -> str:
    """把记录转成 SSE data 行。"""

    return json.dumps(record.to_dict(), ensure_ascii=False)


service = MessageFlowService(db)


__all__ = [
    "FlowRecord",
    "MessageFlowService",
    "message_flow_link",
    "message_flow_url",
    "render_markdown_fragment",
    "sanitize_event_content",
    "service",
    "sse_data",
]
