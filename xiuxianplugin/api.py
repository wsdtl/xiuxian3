import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict
import websockets
from websockets.exceptions import ConnectionClosed


from .schema import loads_message, make_payload, normalize_code


@dataclass
class ClientState:
    """一个 client_id 对应一条 WebSocket 连接。"""

    websocket: Any
    queue: "asyncio.Queue[dict]"
    reader: "asyncio.Task"
    lock: "asyncio.Lock"


class WSClient:
    """WebSocket 测试客户端。

    这个类只做三件事：
    1. 第一次使用 client_id 时，连接 /ws/bot/{client_id}。
    2. 后续相同 client_id 直接复用已有连接。
    3. send(...) 发送一条消息，并等待一条回复。

    注意：当前 ws 驱动器用 code 判断正常或异常。
    code=202 正常，code=404 异常，type 是客户端自定义分类。
    如果 message 没有命中已注册命令，服务端不会回复，send(...) 会超时返回错误。
    """

    def __init__(
        self,
        base_url: str = "ws://frp.dengxiaonan.cn:1234/ws/bot",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.clients: Dict[str, ClientState] = {}
        self._create_lock = asyncio.Lock()

    def _url(self, client_id: str) -> str:
        """生成当前 client_id 的连接地址。"""

        return f"{self.base_url}/{client_id}"

    async def new_client(self, client_id: str) -> ClientState:
        """获取连接；没有就新建，有就复用。"""

        state = self.clients.get(client_id)
        if state and self._is_usable(state):
            return state

        async with self._create_lock:
            state = self.clients.get(client_id)
            if state and self._is_usable(state):
                return state

            if state:
                await self._remove_client(client_id, state)

            websocket = await websockets.connect(self._url(client_id))
            queue: "asyncio.Queue[dict]" = asyncio.Queue()
            reader = asyncio.create_task(self._read_loop(websocket, queue))

            state = ClientState(
                websocket=websocket,
                queue=queue,
                reader=reader,
                lock=asyncio.Lock(),
            )
            self.clients[client_id] = state
            return state

    async def send(self, client_id: str, data: Any) -> dict:
        """发送一条消息，并等待一条服务端回复。"""

        payload = json.dumps(make_payload(data), ensure_ascii=False)

        for attempt in range(2):
            state = await self.new_client(client_id)

            async with state.lock:
                self._clear_queue(state.queue)

                try:
                    await state.websocket.send(payload)
                    reply = await asyncio.wait_for(
                        state.queue.get(),
                        timeout=self.timeout,
                    )
                except asyncio.TimeoutError:
                    return {
                        "code": 404,
                        "type": "text",
                        "message": "等待回复超时：服务端可能没有命中任何触发器",
                    }
                except (ConnectionClosed, OSError, RuntimeError) as exc:
                    await self._remove_client(client_id, state)
                    if attempt == 0:
                        continue
                    return {
                        "code": 404,
                        "type": "text",
                        "message": f"WebSocket 发送失败: {exc}",
                    }

                if reply.get("code") == 404 and state.reader.done():
                    await self._remove_client(client_id, state)

                return reply

        return {
            "code": 404,
            "type": "text",
            "message": "WebSocket 重连失败",
        }

    async def close_all(self) -> None:
        """程序结束时关闭全部连接。"""

        states = list(self.clients.values())
        self.clients.clear()

        for state in states:
            state.reader.cancel()
            await state.websocket.close()

        await asyncio.gather(
            *(state.reader for state in states),
            return_exceptions=True,
        )

    async def _remove_client(self, client_id: str, state: ClientState) -> None:
        """移除一条失效连接；只移除当前对象，避免误删新连接。"""

        if self.clients.get(client_id) is state:
            self.clients.pop(client_id, None)

        state.reader.cancel()
        with suppress(Exception):
            await state.websocket.close()
        await asyncio.gather(state.reader, return_exceptions=True)

    @staticmethod
    def _is_usable(state: ClientState) -> bool:
        """读任务还活着，说明这条连接仍可尝试复用。"""

        return not state.reader.done()

    async def _read_loop(self, websocket: Any, queue: "asyncio.Queue[dict]") -> None:
        """持续读取服务端推送，并放入队列。"""

        try:
            async for text in websocket:
                queue.put_nowait(loads_message(text))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            queue.put_nowait(
                {
                    "code": 404,
                    "type": "text",
                    "message": f"WebSocket 读取失败: {exc}",
                }
            )

    @staticmethod
    def _clear_queue(queue: "asyncio.Queue[dict]") -> None:
        """发送前清理旧回复，避免读到上一轮残留。"""

        while not queue.empty():
            queue.get_nowait()

    @staticmethod
    def _normalize_code(code: object) -> int:
        """只允许 202/404 两种状态码，其它值都按 202 处理。"""

        return normalize_code(code)


client = WSClient()
