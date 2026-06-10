"""修仙 WS 回复包装。"""

from __future__ import annotations

from typing import Any

from .common import row_value
from .markdown_utils import markdown_message, split_button_tags
from .sql import db

MAX_REPLY_BUTTONS = 15
DEFAULT_BUTTONS = ("指南", "状态", "修仙信息")
CONTEXT_BUTTONS_BY_GROUP = {
    "玩家": ("签到", "探险", "探险状态", "结束探险", "休息", "结束休息", "背包", "纳戒", "武器", "装备", "源库", "商场推荐"),
    "背包": ("背包", "纳戒", "保险箱", "修仙物品", "特殊自动出售", "商场推荐", "探险"),
    "纳戒": ("纳戒", "背包", "保险箱", "宝石", "洗髓", "武器", "装备", "探险"),
    "保险箱": ("保险箱", "背包", "纳戒", "宝石", "武器", "特殊自动出售"),
    "修仙物品": ("背包", "纳戒", "保险箱", "宝石", "武器", "装备", "铭刻"),
    "修仙百科": ("修仙百科 武器", "修仙百科 宝石", "修仙百科 跑商", "修仙百科 首领", "修仙百科 断念杖"),
    "源库": ("源库", "源库结息", "升级源库", "签到", "商场推荐", "特殊自动出售", "探险"),
    "商场": ("商场推荐", "商场列表", "商场自动出售", "特殊自动出售", "跑商奖励", "跑商限制", "背包", "源库", "地图"),
    "二手市场": ("二手市场", "背包", "纳戒", "武器", "源库", "商场推荐"),
    "探险": ("探险状态", "结束探险", "探险记录", "探险列表", "背包", "纳戒", "休息", "特殊自动出售"),
    "武器": ("武器", "纳戒", "保险箱", "装备", "铭刻", "探险", "修仙百科 武器"),
    "装备": ("装备", "孔位", "宝石", "纳戒", "武器", "源库", "探险"),
    "铭刻": ("铭刻", "铭刻之羽", "首领", "武器", "装备", "纳戒", "修仙百科 铭刻"),
    "对战": ("状态", "修仙信息", "休息", "决斗记录", "背包", "纳戒", "特殊自动出售"),
    "修仙界历史": ("风云榜", "修仙早报", "修仙界历史", "商场推荐", "首领", "虫洞"),
    "首领": ("首领", "首领状态", "挑战首领", "首领奖励", "状态", "休息", "纳戒"),
    "异界虫洞": ("虫洞", "虫洞状态", "挑战虫洞", "虫洞奖励", "商场推荐", "状态", "休息"),
    "wormhole_service": ("虫洞", "虫洞状态", "挑战虫洞", "虫洞奖励", "商场推荐", "状态", "休息"),
}
PREDICTIVE_BUTTON_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("没有创建用户", "还没有创建用户", "未建档"), ("指南", "修仙帮助")),
    (("血气不足", "精神不足", "重伤", "血气恢复", "精神恢复"), ("休息", "结束休息", "状态", "纳戒")),
    (("探险中", "可领取探险", "结束探险", "探险还没有", "秘境冷却", "预计算"), ("探险状态", "结束探险", "状态")),
    (("没有探险", "没有可领取探险", "探险地点", "当前位置不是探险地点"), ("探险列表", "地图", "探险")),
    (("背包空间不足", "背包已满", "负重", "格子不足"), ("背包", "特殊自动出售", "保险箱", "商场推荐")),
    (("纳戒", "恢复药", "自动用药", "洗髓液"), ("纳戒", "洗髓", "探险")),
    (("源石不足", "源库", "结息", "存入源石", "取出源石"), ("源库", "源库结息", "商场推荐", "特殊自动出售")),
    (("商场", "跑商", "行情", "特殊收购", "导航", "当前位置不是商场地点"), ("商场推荐", "商场列表", "跑商奖励", "地图")),
    (("宝石", "孔位", "镶嵌", "开孔"), ("宝石", "孔位", "装备", "纳戒")),
    (("武器", "附魔", "技能书", "传奇"), ("武器", "纳戒", "铭刻", "修仙百科 武器")),
    (("铭刻", "铭刻之羽"), ("铭刻", "铭刻之羽", "首领")),
    (("首领", "岁时情劫"), ("首领", "首领状态", "挑战首领", "首领奖励")),
    (("虫洞", "异界"), ("虫洞", "虫洞状态", "挑战虫洞", "虫洞奖励")),
    (("切磋", "决斗", "抢劫", "仇恨", "死敌", "报复"), ("决斗记录", "状态", "休息")),
    (("风云榜", "早报", "人物志", "历史"), ("风云榜", "修仙早报", "修仙界历史")),
    (("保险箱",), ("保险箱", "背包", "纳戒", "武器")),
)


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
        "message": markdown_message(
            content,
            _button_commands(commands, service, auto_buttons, default_buttons, content),
            limit=MAX_REPLY_BUTTONS,
        ),
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
        return markdown_message(
            content,
            _button_commands(commands, service, auto_buttons, default_buttons, content),
            limit=MAX_REPLY_BUTTONS,
        )

    content, commands = split_button_tags(_prefix_text(header, message.get("content", "")))
    commands.extend(_keyboard_commands(message))
    return markdown_message(
        content,
        _button_commands(commands, service, auto_buttons, default_buttons, content),
        limit=MAX_REPLY_BUTTONS,
    )


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

    name = str(row_value(row, "display_name", "未建档") or "未建档")
    title = str(row_value(row, "title", "无") or "无")
    level = int(row_value(row, "level", 1) or 1)
    return f"【{name}·{title} Lv.{level}】"


def _button_commands(
    commands: list[Any],
    service: Any = None,
    auto_buttons: bool = True,
    default_buttons: bool = True,
    content: str = "",
) -> list[Any]:
    """收集候选按钮；去重和 15 个上限由 markdown_utils 统一处理。

    顺序固定为：业务手写按钮、正文预测按钮、当前组件按钮、默认按钮。
    """

    result: list[Any] = [*commands]
    if auto_buttons:
        result.extend(_predict_button_commands(content))
        result.extend(_context_button_commands(service))
    if default_buttons:
        result.extend(DEFAULT_BUTTONS)
    return result


def _predict_button_commands(content: str) -> list[str]:
    """根据回复正文预判用户下一步可能要做的固定命令。"""

    text = str(content)
    if not text:
        return []
    commands: list[str] = []
    for keywords, buttons in PREDICTIVE_BUTTON_RULES:
        if any(keyword in text for keyword in keywords):
            commands.extend(buttons)
    return commands


def _context_button_commands(service: Any) -> list[str]:
    """读取当前组件配置的候选按钮。"""

    commands: list[str] = []
    for command in CONTEXT_BUTTONS_BY_GROUP.get(_service_group(service), ()):
        value = str(command).strip()
        if value:
            commands.append(value)
    return commands


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
