"""修仙 WS 回复包装。"""

from __future__ import annotations

from typing import Any

from .markdown_utils import markdown_message, split_button_tags
from .sql import db

MAX_REPLY_BUTTONS = 15
DEFAULT_BUTTONS = ("指南", "探险", "状态")
CONTEXT_BUTTONS_BY_GROUP = {
    "玩家": ("签到", "地图", "探险状态", "结束探险", "休息", "结束休息", "背包", "纳戒", "武器", "装备", "源库", "商场推荐"),
    "背包": ("纳戒", "商场推荐", "特殊自动出售", "探险"),
    "纳戒": ("背包", "洗髓", "宝石", "武器", "装备"),
    "修仙物品": ("背包", "纳戒", "武器", "装备"),
    "源库": ("源库结息", "签到", "商场推荐", "探险"),
    "商场": ("商场推荐", "商场列表", "商场自动出售", "特殊自动出售", "背包", "源库", "地图", "跑商奖励"),
    "二手市场": ("二手市场", "二手市场下架", "背包", "纳戒", "武器", "源库"),
    "探险": ("探险状态", "结束探险", "背包", "纳戒", "休息", "特殊自动出售", "探险记录"),
    "武器": ("武器", "纳戒", "装备", "探险"),
    "装备": ("装备", "宝石", "纳戒", "武器"),
    "铭刻": ("铭刻之羽", "首领", "武器", "装备", "纳戒"),
    "对战": ("状态", "休息", "背包", "特殊自动出售", "决斗记录"),
    "修仙界历史": ("风云榜", "修仙早报", "修仙界历史", "商场推荐", "首领"),
    "首领": ("首领", "挑战首领", "首领奖励", "状态", "休息"),
    "异界虫洞": ("虫洞", "挑战虫洞", "虫洞奖励", "商场推荐", "状态"),
    "wormhole_service": ("虫洞", "挑战虫洞", "虫洞奖励", "商场推荐", "状态"),
}


async def send_reply(client_id: str, message: Any, manager: Any, service: Any = None) -> None:
    """发送修仙回复，并统一加玩家头和默认按钮。"""

    database = getattr(service, "db", None) or db
    await manager.send(_with_player_name(client_id, message, database, service), client_id)


def _with_player_name(client_id: str, message: Any, database: Any, service: Any = None) -> Any:
    """给 text/markdown 回复加玩家头，并把手写按钮标记转成按钮。"""

    header = _player_header(client_id, database)
    if not isinstance(message, dict):
        return _text_to_markdown(header, message, service)

    payload = dict(message)
    auto_buttons = bool(payload.pop("auto_buttons", True))
    default_buttons = bool(payload.pop("default_buttons", True))
    if payload.get("type") == "text":
        return _text_payload(header, payload, service, auto_buttons, default_buttons)
    if payload.get("type") == "markdown":
        payload["message"] = _prefix_markdown(header, payload.get("message"), service, auto_buttons, default_buttons)
    return payload


def _text_payload(header: str, payload: dict, service: Any, auto_buttons: bool, default_buttons: bool) -> dict:
    """处理标准 text 回复；修仙文本统一升级成 markdown。"""

    message = _text_to_markdown(header, payload.get("message", ""), service, auto_buttons, default_buttons)
    payload["type"] = "markdown"
    payload["message"] = message["message"]
    return payload


def _text_to_markdown(
    header: str,
    message: Any,
    service: Any = None,
    auto_buttons: bool = True,
    default_buttons: bool = True,
) -> dict:
    """普通文本先加玩家头，再转成带默认按钮的 markdown。"""

    content, commands = split_button_tags(_prefix_text(header, message))
    return {
        "code": 202,
        "type": "markdown",
        "message": markdown_message(content, _button_commands(commands, service, auto_buttons, default_buttons)),
    }


def _prefix_markdown(
    header: str,
    message: Any,
    service: Any,
    auto_buttons: bool,
    default_buttons: bool,
) -> dict:
    """给已有 markdown 正文加玩家头，并补齐默认按钮。"""

    if not isinstance(message, dict):
        content, commands = split_button_tags(_prefix_text(header, message))
        return markdown_message(content, _button_commands(commands, service, auto_buttons, default_buttons))

    content, commands = split_button_tags(_prefix_text(header, message.get("content", "")))
    commands.extend(_keyboard_commands(message))
    return markdown_message(content, _button_commands(commands, service, auto_buttons, default_buttons))


def _prefix_text(header: str, message: Any) -> str:
    """生成带玩家头的文本。"""

    text = str(message)
    if text.startswith(header):
        return text
    return f"{header}\n{text}".strip()


def _player_header(client_id: str, database: Any) -> str:
    """读取玩家头；未建档或数据库不可用时返回固定名称。"""

    try:
        row = database.fetch_one(
            """
            SELECT p.display_name, p.level, t.title
            FROM players AS p
            LEFT JOIN player_titles AS t
              ON t.client_id = p.client_id AND t.active = 1
            WHERE p.client_id = ?
            """,
            (client_id,),
        )
    except Exception:
        return "【未建档】"
    if not row:
        return "【未建档】"

    name = str(_row_value(row, "display_name", "未建档") or "未建档")
    title = str(_row_value(row, "title", "无") or "无")
    level = int(_row_value(row, "level", 1) or 1)
    return f"【{name}·{title} Lv.{level}】"


def _button_commands(
    commands: list[Any],
    service: Any = None,
    auto_buttons: bool = True,
    default_buttons: bool = True,
) -> list[Any]:
    """业务手写按钮在前，组件按钮居中，默认按钮在后，最终最多 15 个。"""

    manual = _unique_commands(commands)
    defaults = _unique_commands(DEFAULT_BUTTONS) if default_buttons else []
    context = _context_button_commands(service, manual, defaults) if auto_buttons else []
    return _unique_commands((*manual, *context, *defaults), MAX_REPLY_BUTTONS)


def _context_button_commands(service: Any, manual: list[Any], defaults: list[Any]) -> list[str]:
    """只在当前组件按钮里过滤重复项。"""

    occupied = {_command_key(item) for item in (*manual, *defaults)}
    result: list[str] = []
    for command in CONTEXT_BUTTONS_BY_GROUP.get(_service_group(service), ()):
        value = str(command).strip()
        if value and value not in occupied and value not in result:
            result.append(value)
    return result


def _unique_commands(commands: Any, limit: int | None = None) -> list[Any]:
    """按原顺序去重；limit 存在时截断到指定数量。"""

    result: list[Any] = []
    seen: set[str] = set()
    for command in commands:
        value = _normalize_command(command)
        key = _command_key(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
            if limit is not None and len(result) >= limit:
                break
    return result


def _normalize_command(command: Any) -> Any:
    """标准化按钮命令；字符串会去空白，完整按钮对象原样保留。"""

    if isinstance(command, dict):
        return command
    return str(command).strip()


def _command_key(command: Any) -> str:
    """生成按钮去重 key；完整按钮优先使用 action.data。"""

    if isinstance(command, dict):
        action = command.get("action", {})
        if isinstance(action, dict):
            data = str(action.get("data", "")).strip()
            if data:
                return data
        render_data = command.get("render_data", {})
        if isinstance(render_data, dict):
            label = str(render_data.get("label", "")).strip()
            if label:
                return label
        return str(command).strip()
    return _string_command_key(str(command))


def _string_command_key(command: str) -> str:
    """字符串按钮按 `<真实命令:显示文字>` 的真实命令去重。"""

    value = command.strip()
    for separator in (":", "："):
        if separator not in value:
            continue
        cmd_data, label = value.split(separator, 1)
        if label.strip() and cmd_data.strip():
            return cmd_data.strip()
        break
    return value


def _service_group(service: Any) -> str:
    """从 service 所在模块推断当前二级组件。"""

    module = str(getattr(type(service), "__module__", "")) if service is not None else ""
    parts = module.split(".")
    if len(parts) >= 2 and parts[-1] == "service":
        return parts[-2]
    return parts[-1] if parts else ""


def _keyboard_commands(message: dict) -> list[Any]:
    """从已有 markdown keyboard 中取出完整按钮，避免丢失自定义 cmd_data。"""

    rows = (
        message.get("keyboard", {})
        .get("content", {})
        .get("rows", [])
    )
    commands: list[Any] = []
    if not isinstance(rows, list):
        return commands
    for row in rows:
        buttons = row.get("buttons", []) if isinstance(row, dict) else []
        if not isinstance(buttons, list):
            continue
        for item in buttons:
            if not isinstance(item, dict):
                continue
            commands.append(item)
    return commands


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    """兼容 sqlite Row 和测试 dict。"""

    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default
