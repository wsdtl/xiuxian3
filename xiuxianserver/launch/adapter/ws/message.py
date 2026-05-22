import json
import asyncio
from typing import Any, Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .manager import current_request_id, manager
from launch.log import C, logger
from .schema import normalize_code
from .hander import WsMessageHandler
from .rule import RateLimiter, TaskLimiter

router = APIRouter()

# 通用 WebSocket 入口，通过 URL 中的 client_id 区分连接。
WS_ROUTE = "/ws/bot/{client_id}"

# WebSocket 消息后台任务最大并发数。
WS_MAX_CONCURRENT_TASKS = 1000

# WebSocket 消息后台任务最大排队数，超过后直接拒绝本次消息。
WS_MAX_WAITING_TASKS = 5000

# 单个 client_id 最多保留的待处理消息数。
# 同一用户的消息会串行执行，手快连发时超过这个数量就拒绝，避免单个用户拖住太多资源。
WS_CLIENT_MAX_WAITING_TASKS = 5

# WebSocket 消息后台任务超时时间，超过后取消本次触发器分发。
# 比测试客户端 WSClient 的默认 10 秒略短，避免客户端先自己超时。
WS_MESSAGE_TASK_TIMEOUT = 9.0

# WebSocket 连接频率限制。
WS_CONNECT_LIMIT = 1000
WS_CONNECT_WINDOW_SECONDS = 60

# 保存后台任务引用，避免任务还没执行完就被垃圾回收。
background_tasks = set()

# 每个 client_id 一把锁，保证同一个用户的命令按收到顺序串行处理。
client_task_locks: Dict[str, asyncio.Lock] = {}

# 记录每个 client_id 当前已经预占的任务数，用于限制单用户刷屏。
client_task_counts: Dict[str, int] = {}

# 保护 client_task_locks / client_task_counts。
client_task_guard = asyncio.Lock()

# 所有正常消息共用一个并发限制器。
task_limiter = TaskLimiter(
    max_concurrent=WS_MAX_CONCURRENT_TASKS,
    max_waiting=WS_MAX_WAITING_TASKS,
)


@router.websocket(WS_ROUTE)
@RateLimiter.websocket(limit=WS_CONNECT_LIMIT, window=WS_CONNECT_WINDOW_SECONDS)
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    """WebSocket 连接入口。

    主要流程：
    1. 接受连接，并用 client_id 保存到 manager。
    2. 持续接收客户端文本。
    3. 解析 JSON。
    4. code == 202 时交给 WsMessageHandler.dispatch 做命令分发。
    5. 连接断开后清理当前 client_id。
    """

    await manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            await _handle_raw_message(client_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id, websocket)


async def _handle_raw_message(client_id: str, data: str) -> None:
    """解析客户端原始文本；JSON 无效时只回复当前客户端。"""

    message_data = _loads_message(data)
    if message_data is None:
        await manager.send(
            {
                "code": 404,
                "type": "text",
                "message": "Invalid JSON format",
            },
            client_id,
            is_log=False,
        )
        return

    await _dispatch_message(client_id, message_data)


def _loads_message(data: str) -> Optional[Dict[str, Any]]:
    """把客户端文本解析成 dict；失败时返回 None。"""

    try:
        message_data = json.loads(data)
    except json.JSONDecodeError:
        return None

    if not isinstance(message_data, dict):
        return None
    return message_data


async def _dispatch_message(client_id: str, message_data: Dict[str, Any]) -> None:
    """按 code 分发；code=202 表示正常消息，进入命令分发。"""

    protocol_error = _validate_message_data(message_data)
    if protocol_error:
        await _send_protocol_error(client_id, protocol_error, message_data)
        return

    message_code = normalize_code(message_data["code"])

    if message_code == 202:
        logger.opt(colors=True).success(f"{C.yellow('收到消息')} {C.kv('client', client_id)} {C.kv('body', message_data)}")
        if not await WsMessageHandler.has_match(message_data):
            await _send_unmatched_message(client_id, message_data)
            return

        await _create_message_task(client_id, message_data)
    else:
        logger.opt(colors=True).warning(
            f"{C.warn('收到异常消息')} {C.kv('client', client_id)} {C.kv('body', message_data)}"
        )


def _validate_message_data(message_data: Dict[str, Any]) -> Optional[str]:
    """校验新的 WS 通讯格式；格式不对就不进入业务分发。

    新格式固定为：
    {
        "code": 202,
        "type": "text",
        "message": "命令内容",
        "request_id": "本次请求唯一 id"
    }

    request_id 是客户端等待回复的凭证，所以正常消息必须携带。
    """

    for field in ("code", "type", "message"):
        if field not in message_data:
            return f"WS 消息缺少 {field}"

    if normalize_code(message_data["code"]) != 202:
        return None

    if not str(message_data.get("type") or "").strip():
        return "WS 消息 type 不能为空"

    if not _message_request_id(message_data):
        return "WS 消息缺少 request_id"

    return None


async def _send_protocol_error(
    client_id: str,
    message: str,
    message_data: Dict[str, Any],
) -> None:
    """把协议错误回复给当前连接；能读到 request_id 时就原样带回。"""

    logger.opt(colors=True).warning(
        f"{C.warn('WS 消息格式错误')} {C.kv('client', client_id)} {C.kv('body', message_data)}"
    )
    await manager.send(
        {
            "code": 404,
            "type": "text",
            "message": message,
        },
        client_id,
        is_log=False,
        request_id=_message_request_id(message_data),
    )


async def _send_unmatched_message(client_id: str, message_data: Dict[str, Any]) -> None:
    """命令未命中时立刻结束本次请求，不进入后台队列。"""

    await manager.send(
        {
            "code": 404,
            "type": "text",
            "message": "未命中任何触发器",
        },
        client_id,
        is_log=False,
        request_id=_message_request_id(message_data),
    )


async def _create_message_task(client_id: str, message_data: Dict[str, Any]) -> None:
    """创建后台任务，避免阻塞 WebSocket 接收循环。"""

    if not await _reserve_client_task(client_id):
        logger.opt(colors=True).warning(
            f"{C.warn('WebSocket 单用户消息排队已满')} "
            f"{C.kv('client', client_id)} "
            f"{C.kv('max_waiting', WS_CLIENT_MAX_WAITING_TASKS)}"
        )
        await manager.send(
            {
                "code": 202,
                "type": "text",
                "message": "操作太快，请稍后再试",
            },
            client_id,
            is_log=False,
            request_id=_message_request_id(message_data),
        )
        return

    if not await task_limiter.reserve():
        await _release_client_task(client_id)
        logger.opt(colors=True).warning(
            f"{C.warn('WebSocket 后台任务排队已满')} "
            f"{C.kv('client', client_id)} "
            f"{C.kv('max_waiting', WS_MAX_WAITING_TASKS)}"
        )
        await manager.send(
            {
                "code": 202,
                "type": "text",
                "message": "服务繁忙，请稍后再试",
            },
            client_id,
            is_log=False,
            request_id=_message_request_id(message_data),
        )
        return

    task = asyncio.create_task(_run_message_task(client_id, message_data))
    background_tasks.add(task)
    task.add_done_callback(_on_message_task_done)


async def _run_message_task(client_id: str, message_data: Dict[str, Any]) -> None:
    """在并发限制和超时保护内执行一次消息分发。

    wait_for 包住的是 task_limiter.run(...) 整体：
    - 同一个 client_id 会先等自己的串行锁，避免同用户命令乱序。
    - 如果任务还在等待串行锁或全局并发名额，超时后会释放预占名额。
    - 如果任务已经进入 dispatch，超时后会取消当前触发器协程。
    """

    task_limiter_started = False
    request_token = current_request_id.set(_message_request_id(message_data))

    async def dispatch_with_limit() -> Optional[bool]:
        nonlocal task_limiter_started
        client_lock = await _get_client_task_lock(client_id)
        async with client_lock:
            task_limiter_started = True
            return await task_limiter.run(
                lambda: WsMessageHandler.dispatch(
                    client_id=client_id,
                    message_data=message_data,
                    manager=manager,
                )
            )

    try:
        matched = await asyncio.wait_for(
            dispatch_with_limit(),
            timeout=WS_MESSAGE_TASK_TIMEOUT,
        )
        if matched is False:
            await manager.send(
                {
                    "code": 404,
                    "type": "text",
                    "message": "未命中任何触发器",
                },
                client_id,
                is_log=False,
            )
    except asyncio.TimeoutError:
        logger.opt(colors=True).warning(
            f"{C.warn('WebSocket 后台任务超时，已终止')} "
            f"{C.kv('client', client_id)} "
            f"{C.kv('timeout', WS_MESSAGE_TASK_TIMEOUT)}"
        )
        await manager.send(
            {
                "code": 202,
                "type": "text",
                "message": "触发器执行超时，已终止本次任务",
            },
            client_id,
            is_log=False,
        )
    finally:
        current_request_id.reset(request_token)
        if not task_limiter_started:
            await task_limiter.release_reserved()
        await _release_client_task(client_id)


def _message_request_id(message_data: Dict[str, Any]) -> Optional[str]:
    """读取本次消息的 request_id；没有就返回 None。"""

    request_id = message_data.get("request_id")
    if request_id is None:
        return None

    value = str(request_id).strip()
    return value or None


async def _reserve_client_task(client_id: str) -> bool:
    """为单个 client_id 预占一个待处理名额。"""

    async with client_task_guard:
        count = client_task_counts.get(client_id, 0)
        if count >= WS_CLIENT_MAX_WAITING_TASKS:
            return False

        client_task_counts[client_id] = count + 1
        client_task_locks.setdefault(client_id, asyncio.Lock())
        return True


async def _release_client_task(client_id: str) -> None:
    """释放单个 client_id 的待处理名额。"""

    async with client_task_guard:
        count = client_task_counts.get(client_id, 0) - 1
        if count > 0:
            client_task_counts[client_id] = count
            return

        client_task_counts.pop(client_id, None)
        client_task_locks.pop(client_id, None)


async def _get_client_task_lock(client_id: str) -> asyncio.Lock:
    """读取当前 client_id 的串行锁。"""

    async with client_task_guard:
        return client_task_locks.setdefault(client_id, asyncio.Lock())


async def _handle_message_task_result(task: asyncio.Task) -> None:
    """后台任务结束后的清理和异常日志。"""

    background_tasks.discard(task)

    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.opt(colors=True, exception=exc).error(f"{C.fail('WebSocket 后台任务异常')}")


def _on_message_task_done(task: asyncio.Task) -> None:
    """把 asyncio 的同步 done_callback 转到异步清理函数。"""

    asyncio.create_task(_handle_message_task_result(task))


async def shutdown() -> None:
    """取消后台任务，并关闭所有 WebSocket 连接。"""

    tasks = list(background_tasks)
    for task in tasks:
        task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await manager.close_all()
