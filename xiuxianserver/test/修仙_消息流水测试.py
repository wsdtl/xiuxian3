"""消息流水组件测试。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from launch.message_events import event_from_incoming, event_from_outgoing
from 修仙.identity import bind_client_to_player, ensure_player_identity
from 修仙.消息流水.service import MessageFlowService, render_markdown_fragment, sanitize_event_content
from 修仙.sql import XiuxianDB


async def test_message_flow_records_group_primary_id() -> None:
    """副入口消息应归档到用户组主用户。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "message_flow.db")
        try:
            db.init()
            db.execute(
                """
                INSERT INTO players
                (client_id, display_name, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                ("main_player", "流水道友"),
            )
            ensure_player_identity("main_player", db)
            bind_client_to_player("extra_client", "main_player", db)

            service = MessageFlowService(db)
            await service.start()
            record = await service.record_event(
                event_from_incoming(
                    adapter="ws",
                    client_id="extra_client",
                    request_id="req-1",
                    message_type="text",
                    content="状态",
                )
            )
            assert record is not None
            assert record.client_id == "extra_client"
            assert record.player_id == "main_player"

            rows = await service.recent("main_player", limit=5)
            assert len(rows) == 1
            assert rows[0]["content"] == "状态"
            assert rows[0]["direction"] == "incoming"
        finally:
            db.close()


async def test_outgoing_sanitizes_header_and_notifications() -> None:
    """发出消息只展示业务正文，不展示玩家头、系统栏和个人通知。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "message_flow_clean.db")
        try:
            db.init()
            db.execute(
                """
                INSERT INTO players
                (client_id, display_name, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                ("player_a", "流水道友"),
            )
            service = MessageFlowService(db)
            await service.start()
            event = event_from_outgoing(
                adapter="qq",
                client_id="player_a",
                request_id="event-1",
                message={
                    "type": "markdown",
                    "message": {
                        "content": (
                            "【流水道友·试剑人 LV9】\n"
                            "🔴 系统：[异界虫洞](mqqapi://aio/inlinecmd?command=x&enter=true&reply=false)\n"
                            "🔴 通知：[银行结息](mqqapi://aio/inlinecmd?command=x&enter=true&reply=false)\n"
                            "> **状态**\n"
                            "> 血气 **100/100**\n"
                            "\n"
                            "[战斗日志〔1〕](https://example.com/log/1)"
                        ),
                        "keyboard": {"content": {"rows": [{"buttons": [{"action": {"data": "状态"}}]}]}},
                    },
                },
            )
            assert "🔴 系统" not in sanitize_event_content(event)
            assert "🔴 通知" not in sanitize_event_content(event)
            assert "【流水道友" not in sanitize_event_content(event)

            record = await service.record_event(event)
            assert record is not None
            assert record.message_type == "markdown"
            assert record.content.startswith("> **状态**")
            assert "战斗日志" in record.content

            html = render_markdown_fragment(record.content)
            assert "<blockquote>" in html
            assert "<strong>状态</strong>" in html
            assert 'href="https://example.com/log/1"' in html
            assert "<ul>" not in html
        finally:
            db.close()


def test_markdown_fragment_renders_more_fully() -> None:
    """消息流水富文本应支持标题、列表、代码块和行内代码。"""

    html = render_markdown_fragment(
        "# 标题\n"
        "## 副标题\n"
        "- 第一项\n"
        "1. 第二项\n"
        "```python\n"
        "print('ok')\n"
        "```\n"
        "正文里有 `代码` 和 [链接](https://example.com)\n"
    )
    assert "<h1>" in html
    assert "<h2>" in html
    assert "<ul>" in html
    assert "<ol>" in html
    assert "<pre><code>" in html
    assert "<code>代码</code>" in html
    assert 'href="https://example.com"' in html


async def test_message_flow_retention_keeps_latest_rows() -> None:
    """清理时保留最新记录，过旧记录会被删除。"""

    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "message_flow_retention.db")
        try:
            db.init()
            service = MessageFlowService(db)
            db.execute(
                """
                INSERT INTO message_flows
                (flow_id, direction, adapter, request_id, client_id, player_id, message_type, content, created_at)
                VALUES (1, 'incoming', 'ws', '', 'old', 'old', 'text', '旧消息', '2000-01-01T00:00:00')
                """
            )
            await service.record_event(
                event_from_incoming(adapter="ws", client_id="new", request_id="req", content="新消息")
            )
            service.cleanup()
            rows = db.fetch_all("SELECT content FROM message_flows ORDER BY flow_id")
            assert [row["content"] for row in rows] == ["新消息"]
        finally:
            db.close()


def main() -> None:
    asyncio.run(test_message_flow_records_group_primary_id())
    asyncio.run(test_outgoing_sanitizes_header_and_notifications())
    test_markdown_fragment_renders_more_fully()
    asyncio.run(test_message_flow_retention_keeps_latest_rows())
    print("修仙消息流水测试通过")


if __name__ == "__main__":
    main()
