"""QQ webhook 事件解析。

QQ 原始 payload 保留在 raw 中，但驱动器内部只把命令系统需要的字段
提取成 QqMessageEvent，避免业务派发层反复处理开放平台的原始结构。
"""

import re
from dataclasses import dataclass
from typing import Any, Dict


FIRST_LEADING_MENTION_RE = re.compile(r"^\s*<@([^>]+)>")
LEADING_MENTION_CHAIN_RE = re.compile(r"^(?:\s*<@[^>]+>\s*)+")
MENTION_RE = re.compile(r"<@([^>]+)>")
GROUP_MESSAGE_EVENT_TYPES = {
    "GROUP_AT_MESSAGE_CREATE",
    "GROUP_MESSAGE_AT_CREATE",
    "GROUP_MESSAGE_CREATE",
}


@dataclass(frozen=True)
class QqMessageEvent:
    """QQ 驱动器内部使用的规整消息事件。

    payload 的原始字段在不同事件类型里并不完全一致。这里把命令系统
    必须关心的字段收敛成固定结构：业务身份 client_id、正文 content、
    私聊目标 user_openid、群目标 group_openid，以及原始 raw payload。
    """

    event_type: str
    event_id: str
    message_id: str
    client_id: str
    content: str
    group_openid: str
    user_openid: str
    raw: Dict[str, Any]
    interaction_id: str = ""

    @property
    def is_group(self) -> bool:
        """当前事件是否来自群聊。"""

        return bool(self.group_openid)


def parse_message_event(payload: dict) -> QqMessageEvent | None:
    """从 QQ webhook payload 中提取可处理的消息事件。

    不属于消息创建的事件返回 None，调用方仍会 ACK；字段不完整的消息
    也返回 None，避免后续回复阶段缺少 openid 或 message_id。

    这里故意不抛异常。QQ webhook 的原则是“能 ACK 就先 ACK”，异常 payload
    不应该拖垮整个回调入口。
    """

    data = payload.get("d")
    if not isinstance(data, dict):
        return None

    event_type = str(payload.get("t") or "").strip()
    if event_type == "INTERACTION_CREATE":
        return parse_interaction_event(payload, data)

    if event_type not in {"C2C_MESSAGE_CREATE", *GROUP_MESSAGE_EVENT_TYPES}:
        return None

    content = normalize_content(
        data.get("content"),
        event_type=event_type,
        mentions=data.get("mentions"),
    )
    message_id = str(data.get("id") or "").strip()
    event_id = str(payload.get("id") or "").strip()
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    user_openid = str(
        author.get("user_openid")
        or author.get("member_openid")
        or author.get("id")
        or ""
    ).strip()
    group_openid = str(data.get("group_openid") or data.get("group_id") or "").strip()

    if event_type in GROUP_MESSAGE_EVENT_TYPES and not group_openid:
        return None
    if not content or not message_id or not user_openid:
        return None

    return QqMessageEvent(
        event_type=event_type,
        event_id=event_id,
        message_id=message_id,
        client_id=user_openid,
        content=content,
        group_openid=group_openid,
        user_openid=user_openid,
        raw=payload,
    )


def parse_interaction_event(payload: dict, data: dict) -> QqMessageEvent | None:
    """从 QQ 按钮回调事件中提取可派发的命令事件。

    按钮 action.data 会落到 button_data，驱动器把它当成普通命令正文继续
    派发。interaction_id 额外保留，用于 ACK 点击，避免 QQ 客户端等待失败。
    """

    resolved = _interaction_resolved_data(data)
    content = normalize_content(resolved.get("button_data"))
    interaction_id = str(data.get("id") or payload.get("id") or "").strip()
    event_id = str(payload.get("id") or interaction_id).strip()
    message_id = str(resolved.get("message_id") or "").strip()
    group_openid = str(data.get("group_openid") or data.get("group_id") or "").strip()
    user_openid = str(
        data.get("user_openid")
        or data.get("group_member_openid")
        or resolved.get("user_id")
        or ""
    ).strip()

    if data.get("group_member_openid") and not group_openid:
        return None
    if not content or not interaction_id or not user_openid:
        return None

    return QqMessageEvent(
        event_type="INTERACTION_CREATE",
        event_id=event_id,
        message_id=message_id,
        client_id=user_openid,
        content=content,
        group_openid=group_openid,
        user_openid=user_openid,
        raw=payload,
        interaction_id=interaction_id,
    )


def normalize_content(
    value: Any,
    *,
    event_type: str = "",
    mentions: Any = None,
) -> str:
    """清理 QQ 消息正文，并把 QQ at 段转成业务层可识别的入口 ID。

    群聊里用户通常用“@机器人 命令”触发；开头的机器人 at 只表示触发，
    不应该作为业务参数。正文中其它用户 at 会被替换成入口 ID，供修仙业务
    后续通过用户组映射到角色。
    """

    text = "" if value is None else str(value)
    if _should_strip_leading_mentions(text, event_type, mentions):
        text = LEADING_MENTION_CHAIN_RE.sub("", text, count=1)
    text = _replace_mentions_with_ids(text, mentions)
    return re.sub(r"\s+", " ", text).strip()


def _interaction_resolved_data(data: dict) -> dict:
    """兼容 QQ 文档里的 resolved/resoloved 两种字段写法。"""

    interaction_data = data.get("data")
    if not isinstance(interaction_data, dict):
        return {}
    resolved = interaction_data.get("resolved")
    if isinstance(resolved, dict):
        return resolved
    resoloved = interaction_data.get("resoloved")
    if isinstance(resoloved, dict):
        return resoloved
    if "button_data" in interaction_data:
        return interaction_data
    return {}


def _should_strip_leading_mentions(text: str, event_type: str, mentions: Any) -> bool:
    """判断开头 at 是否确实是在叫当前机器人。"""

    first = FIRST_LEADING_MENTION_RE.search(text)
    if not first:
        return False

    first_mention_id = first.group(1).strip().lstrip("!")
    you_ids = _you_mention_ids(mentions)
    if you_ids:
        return first_mention_id in you_ids

    # 少数 QQ at 机器人事件可能没有 mentions 详情；这种事件本身就代表
    # “用户在叫机器人”，保留兼容处理。
    return event_type in {"GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_AT_CREATE"}


def _you_mention_ids(mentions: Any) -> set[str]:
    """从 QQ mentions 列表里提取当前机器人的 mention ID。"""

    if not isinstance(mentions, list):
        return set()

    result: set[str] = set()
    for item in mentions:
        if not isinstance(item, dict):
            continue
        if not _is_you_mention(item.get("is_you")):
            continue
        for key in ("id", "member_openid", "user_openid"):
            value = str(item.get(key) or "").strip().lstrip("!")
            if value:
                result.add(value)
    return result


def _replace_mentions_with_ids(text: str, mentions: Any) -> str:
    """把正文里的 <@...> 替换成前后带空格的入口 ID。

    修仙业务层已经约定：需要指定玩家的命令接收普通文本参数，平台 at
    需要先在驱动器层转换成原始入口 ID，再由用户组解析成主角色 ID。
    机器人自己的 at 只表示“叫机器人处理这条消息”，不属于业务参数。
    """

    mention_ids = _mention_id_map(mentions)
    you_ids = _you_mention_ids(mentions)

    def replace(match: re.Match) -> str:
        token = match.group(1).strip().lstrip("!")
        if token in you_ids:
            return " "
        value = mention_ids.get(token) or token
        return f" {value} " if value else " "

    return MENTION_RE.sub(replace, text)


def _mention_id_map(mentions: Any) -> dict[str, str]:
    """建立 QQ mention 占位 ID 到入口 ID 的映射。

    QQ payload 里正文 `<@...>` 使用的 ID 和 mentions 详情字段可能不完全
    同名。这里把 id、user_openid、member_openid 都登记为可匹配键，值优先
    取 user_openid，保持和事件 client_id 的选择顺序一致。
    """

    if not isinstance(mentions, list):
        return {}

    result: dict[str, str] = {}
    for item in mentions:
        if not isinstance(item, dict):
            continue

        preferred = _preferred_mention_id(item)
        if not preferred:
            continue

        for key in ("id", "user_openid", "member_openid"):
            token = str(item.get(key) or "").strip().lstrip("!")
            if token:
                result[token] = preferred
    return result


def _preferred_mention_id(item: dict) -> str:
    """读取 mention 对应的业务入口 ID，顺序和消息作者 client_id 保持一致。"""

    for key in ("user_openid", "member_openid", "id"):
        value = str(item.get(key) or "").strip().lstrip("!")
        if value:
            return value
    return ""


def _is_you_mention(value: Any) -> bool:
    """兼容 bool 和字符串形式的 is_you。"""

    if value is True:
        return True
    return str(value).strip().lower() in {"1", "true", "yes"}
