"""QQ 回复管理器。

业务层通过统一 manager.send(...) 回复消息；QQ 驱动器在这里把业务
返回值转换成 QQ OpenAPI 可发送的载荷，并根据当前事件上下文选择
私聊或群聊接口。
"""

import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass
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


@dataclass(frozen=True)
class QqQueuedReply:
    """QQ 待发送回复。

    manager.send 只负责捕获当前事件上下文并入队；真正的 OpenAPI 请求
    由后台 worker 执行，避免业务命令被 QQ 网络耗时拖住。
    """

    message: object
    event: QqMessageEvent
    client_id: str
    is_log: bool = True
    request_id: object | None = None


class QqReplyManager:
    """按当前 QQ 事件上下文发送私聊或群聊回复。

    业务层只传入 message 和 client_id；QQ 真正发消息还需要知道本次
    webhook 是 C2C 还是群事件，以及原始 message_id/event_id。handler
    处理事件前会把 QqMessageEvent 放进 current_event，回复器从这里
    取 QQ 私有上下文，再调用对应 OpenAPI。
    """

    SEND_WORKERS = 8
    MAX_WAITING_REPLIES = 1000
    SHUTDOWN_DRAIN_SECONDS = 3.0

    def __init__(self) -> None:
        self._send_queue: asyncio.Queue[QqQueuedReply] | None = None
        self._send_tasks: set[asyncio.Task] = set()
        self._warmup_task: asyncio.Task | None = None
        self._send_executor: ThreadPoolExecutor | None = None

    async def start(self) -> None:
        """启动 QQ 回复发送队列，并在后台预热 access token。

        回复 worker 是固定数量的常驻协程。业务层调用 manager.send 时只入队，
        不等待 QQ OpenAPI；真正的网络请求由 worker 在后台执行。
        """

        if self._send_tasks:
            return

        self._send_executor = ThreadPoolExecutor(
            max_workers=self.SEND_WORKERS,
            thread_name_prefix="qq-send",
        )
        self._send_queue = asyncio.Queue(maxsize=self.MAX_WAITING_REPLIES)
        for index in range(self.SEND_WORKERS):
            task = asyncio.create_task(self._send_worker(index), name=f"qq-send-worker-{index}")
            self._send_tasks.add(task)
            task.add_done_callback(self._send_tasks.discard)

        if client.has_credentials:
            self._warmup_task = asyncio.create_task(
                self._warmup_access_token(),
                name="qq-access-token-warmup",
            )

    async def shutdown(self) -> None:
        """停止 QQ 回复发送队列，并释放 HTTP 连接池。

        关闭时先短暂等待队列清空，给已经接收的回复一个发送机会；超过
        SHUTDOWN_DRAIN_SECONDS 仍未发完，就丢弃剩余项，避免停服时一直挂住。
        """

        if self._warmup_task is not None:
            self._warmup_task.cancel()
            await asyncio.gather(self._warmup_task, return_exceptions=True)
            self._warmup_task = None

        queue = self._send_queue
        if queue is not None:
            try:
                await asyncio.wait_for(queue.join(), timeout=self.SHUTDOWN_DRAIN_SECONDS)
            except asyncio.TimeoutError:
                dropped = self._drop_waiting_replies(queue)
                logger.opt(colors=True).warning(
                    C.join(
                        C.warn("QQ 回复队列关闭等待超时，丢弃剩余回复"),
                        C.kv("dropped", dropped),
                        C.kv("waiting", queue.qsize()),
                    )
                )

        tasks = list(self._send_tasks)
        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._send_tasks.clear()
        self._send_queue = None
        self._shutdown_executor()
        client.close()

    def _shutdown_executor(self) -> None:
        """关闭 QQ 发送专用线程池，避免 OpenAPI 线程散落到全局线程池。"""

        executor = self._send_executor
        self._send_executor = None
        if executor is None:
            return
        executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _drop_waiting_replies(queue: asyncio.Queue[QqQueuedReply]) -> int:
        """丢弃还没有被 worker 取走的回复项，保证 queue.join() 不残留。"""

        dropped = 0
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return dropped

            queue.task_done()
            dropped += 1

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

        item = QqQueuedReply(
            message=message,
            event=event,
            client_id=client_id,
            is_log=is_log,
            request_id=request_id,
        )

        queue = self._send_queue
        if queue is None:
            if is_log:
                logger.opt(colors=True).warning(
                    C.join(
                        C.warn("QQ 回复队列未启动"),
                        *self._reply_log_parts(item),
                    )
                )
            return False

        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            if is_log:
                logger.opt(colors=True).warning(
                    C.join(
                        C.warn("QQ 回复队列已满"),
                        *self._reply_log_parts(item),
                        C.kv("max_waiting", self.MAX_WAITING_REPLIES),
                    )
                )
            return False

        if is_log:
            logger.opt(colors=True).debug(
                C.join(
                    C.ok("QQ 回复已入队"),
                    *self._reply_log_parts(item),
                )
            )
        return True

    async def _send_worker(self, index: int) -> None:
        """后台发送 QQ 回复。

        worker 自己兜住单条发送异常，避免某次 OpenAPI 报错把整个发送协程
        打死。只有 shutdown cancel 时才退出循环。
        """

        queue = self._send_queue
        if queue is None:
            return

        try:
            while True:
                item = await queue.get()
                try:
                    await self._send_direct(item)
                except Exception as exc:
                    logger.opt(colors=True, exception=exc).warning(
                        C.join(
                            C.warn("QQ 回复 worker 异常"),
                            C.kv("worker", index),
                        )
                    )
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            return

    async def _warmup_access_token(self) -> None:
        """后台预热 access token，让第一条回复少等一次 token 请求。"""

        try:
            await self._run_sync(client.get_access_token)
            logger.opt(colors=True).debug(f"{C.ok('QQ access token 已预热')}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.opt(colors=True, exception=exc).warning(f"{C.warn('QQ access token 预热失败')}")

    async def _send_direct(self, item: QqQueuedReply) -> bool:
        """执行一次 QQ 回复发送，供队列 worker 和兜底路径共用。"""

        try:
            payload = await self._run_sync(self._send_sync, item.message, item.event)
        except Exception as exc:
            logger.opt(colors=True, exception=exc).warning(
                C.join(
                    C.warn("QQ 回复发送失败"),
                    *self._reply_log_parts(item),
                )
            )
            return False

        if not payload:
            return False

        if item.is_log:
            logger.opt(colors=True).debug(
                C.join(
                    C.ok("QQ 回复已发送"),
                    *self._reply_log_parts(item),
                    C.kv("msg_type", payload.get("msg_type") or "-"),
                )
            )
        return True

    async def _run_sync(self, func, *args):
        """在 QQ 发送专用线程池里运行同步 OpenAPI 调用。

        发送链路必须走本驱动器自己的线程池，便于统一关闭和排查线程残留。
        如果这里没有线程池，说明 manager.start() 没有按生命周期执行。
        """

        executor = self._send_executor
        if executor is None:
            raise RuntimeError("QQ 发送线程池未启动")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, func, *args)

    @staticmethod
    def _send_sync(message: object, event: QqMessageEvent) -> dict:
        """在线程中执行 QQ OpenAPI 调用，避免阻塞 async 事件循环。"""

        payload = QqReplyManager._message_payload(message, event)
        if not payload:
            return {}

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
        return payload

    @staticmethod
    def _reply_log_parts(item: QqQueuedReply) -> list[str]:
        """生成 QQ 回复日志摘要。"""

        return [
            C.kv("type", "群聊" if item.event.is_group else "私聊"),
            C.kv("client", QqReplyManager._short_id(item.client_id)),
            C.kv("request_id", item.request_id or "-"),
        ]

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


manager = QqReplyManager()
