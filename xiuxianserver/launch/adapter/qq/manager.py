"""QQ 回复管理器。

业务层通过统一 manager.send(...) 回复消息；QQ 驱动器在这里把业务
返回值转换成 QQ OpenAPI 可发送的载荷，并根据当前事件上下文选择
私聊或群聊接口。
"""

import json
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from typing import Any

from launch.log import C, logger

from .client import client
from .event import QqMessageEvent


current_event: ContextVar[QqMessageEvent | None] = ContextVar(
    "qq_current_event",
    default=None,
)


class QqReplyManager:
    """按当前 QQ 事件上下文发送私聊或群聊回复。

    业务层只传入 message 和 client_id；QQ 真正发消息还需要知道本次
    webhook 是 C2C 还是群事件，以及原始 message_id/event_id。handler
    处理事件前会把 QqMessageEvent 放进 current_event，回复器从这里
    取 QQ 私有上下文，再调用对应 OpenAPI。
    """

    async def send(
        self,
        message: object,
        client_id: str,
        is_log: bool = True,
        request_id: object | None = None,
    ) -> bool:
        """发送一条 QQ 回复。

        client_id 保持项目统一回复接口的参数形状；QQ 实际发送目标以
        current_event 为准，避免业务层直接接触 group_openid/user_openid。
        """

        event = current_event.get()
        if event is None:
            if is_log:
                logger.opt(colors=True).warning(f"{C.warn('QQ 回复失败，缺少当前事件上下文')}")
            return False

        try:
            payload = self._message_payload(message, event)
            if not payload:
                return False

            if event.is_group:
                client.send_group_payload(
                    event.group_openid,
                    payload,
                    event.message_id,
                    event.event_id,
                )
            else:
                client.send_c2c_payload(
                    event.user_openid,
                    payload,
                    event.message_id,
                    event.event_id,
                )
        except Exception as exc:
            logger.opt(colors=True, exception=exc).warning(f"{C.warn('QQ 回复发送失败')}")
            return False

        if is_log:
            logger.opt(colors=True).debug(
                C.join(
                    C.ok("QQ 回复已发送"),
                    C.kv("type", "群聊" if event.is_group else "私聊"),
                    C.kv("client", self._short_id(client_id)),
                    C.kv("request_id", request_id or "-"),
                )
            )
        return True

    @staticmethod
    def _message_payload(message: object, event: QqMessageEvent) -> dict:
        """把业务返回值转换成 QQ OpenAPI 消息载荷。

        项目内的 text / markdown / image 是业务层统一回复格式；QQ
        开放接口发送 markdown 和图片时都有专门载荷，不能把原始对象
        当普通 content 发。
        """

        if isinstance(message, dict):
            message_type = str(message.get("type") or "").lower()
            if message_type == "markdown":
                return QqReplyManager._markdown_payload(message.get("message"))
            if message_type == "image":
                return QqReplyManager._image_payload(message.get("message"), event)

            value = message.get("message", "")
            content = QqReplyManager._message_text(value)
            return QqReplyManager._text_payload(content)

        content = QqReplyManager._message_text(message)
        return QqReplyManager._text_payload(content)

    @staticmethod
    def _markdown_payload(message: object) -> dict:
        """生成 QQ markdown 消息载荷，保留业务层已经生成的按钮。"""

        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()
            if not content:
                return {}

            payload: dict[str, Any] = {
                "content": " ",
                "msg_type": 2,
                "markdown": {"content": content},
            }
            keyboard = message.get("keyboard")
            if QqReplyManager._has_keyboard_buttons(keyboard):
                payload["keyboard"] = keyboard
            return payload

        content = QqReplyManager._message_text(message)
        if not content:
            return {}
        return {
            "content": " ",
            "msg_type": 2,
            "markdown": {"content": content},
        }

    @staticmethod
    def _image_payload(message: object, event: QqMessageEvent) -> dict:
        """生成 QQ 纯图片消息载荷。

        QQ 纯图片回复不能直接把 BytesIO/bytes 塞进发消息接口，需要先上传
        到当前会话的 /files 接口拿 file_info，再用 msg_type=7 发送 media。
        """

        image_bytes = QqReplyManager._read_image_bytes(message)
        if not image_bytes:
            raise ValueError("QQ 图片消息内容为空或格式不支持")

        if event.is_group:
            file_info = client.upload_group_image(event.group_openid, image_bytes)
        else:
            file_info = client.upload_c2c_image(event.user_openid, image_bytes)

        return {
            "content": " ",
            "msg_type": 7,
            "media": {"file_info": file_info},
        }

    @staticmethod
    def _text_payload(content: str) -> dict:
        """生成 QQ 普通文本消息载荷。"""

        content = str(content).strip()
        if not content:
            return {}
        return {
            "content": content,
            "msg_type": 0,
        }

    @staticmethod
    def _message_text(message: object) -> str:
        """把非 markdown 回复整理成普通文本。"""

        if isinstance(message, dict):
            if "content" in message:
                return str(message.get("content") or "").strip()
            if "message" in message:
                return QqReplyManager._message_text(message.get("message"))
            return json.dumps(message, ensure_ascii=False, default=str)
        if isinstance(message, (list, tuple)):
            return "\n".join(str(item) for item in message if str(item).strip()).strip()
        if message is None:
            return ""
        return str(message).strip()

    @staticmethod
    def _read_image_bytes(message: object) -> bytes:
        """读取图片二进制，支持 bytes、BytesIO 和 Path。"""

        if isinstance(message, bytes):
            return message
        if isinstance(message, bytearray | memoryview):
            return bytes(message)
        if isinstance(message, BytesIO):
            position = message.tell()
            message.seek(0)
            data = message.read()
            message.seek(position)
            return data
        if isinstance(message, Path):
            return message.read_bytes()
        if hasattr(message, "read"):
            return QqReplyManager._read_file_like_bytes(message)
        return b""

    @staticmethod
    def _read_file_like_bytes(message: object) -> bytes:
        """读取类文件对象，尽量恢复原始指针位置。"""

        position = None
        try:
            if hasattr(message, "tell"):
                position = message.tell()
            if hasattr(message, "seek"):
                message.seek(0)
            data = message.read()
        finally:
            if position is not None and hasattr(message, "seek"):
                message.seek(position)

        if isinstance(data, str):
            return data.encode("utf-8")
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray | memoryview):
            return bytes(data)
        return b""

    @staticmethod
    def _has_keyboard_buttons(value: object) -> bool:
        """判断 QQ keyboard 中是否真的有按钮，避免发送空键盘。"""

        if not isinstance(value, dict):
            return False
        if value.get("id"):
            return True
        content = value.get("content", {})
        if not isinstance(content, dict):
            return False
        rows = content.get("rows", [])
        if not isinstance(rows, list):
            return False
        return any(
            isinstance(row, dict) and bool(row.get("buttons"))
            for row in rows
        )

    @staticmethod
    def _short_id(value: object, head: int = 8, tail: int = 6) -> str:
        """缩短开放平台长 ID，避免正常回复日志过长。"""

        text = str(value or "").strip()
        if not text:
            return "-"
        if len(text) <= head + tail + 3:
            return text
        return f"{text[:head]}...{text[-tail:]}"

    @staticmethod
    def dump(message: Any) -> str:
        """调试用：把任意消息对象转成 JSON 字符串。"""

        return json.dumps(message, ensure_ascii=False, default=str)


manager = QqReplyManager()
