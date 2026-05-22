import json
from typing import Any


def normalize_code(code: object) -> int:
    """把 code 统一成 202 或 404。

    支持数字和字符串：
    - 202 / "202" -> 202
    - 404 / "404" -> 404
    - 其它值 -> 202
    """

    try:
        code_value = int(code)
    except (TypeError, ValueError):
        return 202

    return 404 if code_value == 404 else 202


def ws_message(
    message: object,
    message_type: str = "text",
    code: object = 202,
) -> dict:
    """生成统一的 WS 消息格式。

    字段顺序固定，不能调换：
    - code: 202 表示正常，404 表示异常。
    - type: 自定义消息类型，默认 text。
    - message: 文本内容。
    """

    return {
        "code": normalize_code(code),
        "type": str(message_type),
        "message": str(message),
    }


def make_payload(data: Any) -> dict:
    """把任意输入转成 WS 统一格式。"""

    if isinstance(data, dict):
        return ws_message(
            message=data.get("message", ""),
            message_type=data.get("type", "text"),
            code=data.get("code", 202),
        )

    return ws_message(data)


def loads_message(text: str) -> dict:
    """解析 WS 文本消息，并统一成 code/type/message 三个字段。"""

    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        return ws_message(text)

    return make_payload(message)
