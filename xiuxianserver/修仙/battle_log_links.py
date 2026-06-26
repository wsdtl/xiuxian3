"""战斗日志链接生成。"""

from __future__ import annotations

from .markdown_utils import markdown_link
from .public_url import public_url


LOG_BASE_PATH = "/xiuxian/zhandou-rizhi"


def battle_log_url(kind: str, record_id: int, *, client_id: str = "", detail: bool = False) -> str:
    """生成可直接打开的完整战斗日志地址。"""

    query: list[str] = []
    if client_id:
        query.append(f"player={client_id}")
    if detail:
        query.append("detail=1")
    suffix = f"?{'&'.join(query)}" if query else ""
    return public_url(f"{LOG_BASE_PATH}/{kind}/{int(record_id)}{suffix}")


def battle_log_markdown(label: str, kind: str, record_id: int, *, client_id: str = "", detail: bool = False) -> str:
    """生成消息里使用的 Markdown 改名链接。"""

    return markdown_link(label, battle_log_url(kind, record_id, client_id=client_id, detail=detail))
