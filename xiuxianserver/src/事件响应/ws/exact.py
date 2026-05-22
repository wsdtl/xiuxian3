from launch.adapter.ws import ConnectionManager, WsMessageHandler


@WsMessageHandler.handler(cmd="你好", priority=10, block=False)
async def hello(
    client_id: str,
    message: str,
    manager: "ConnectionManager",
) -> None:
    """WebSocket 精确命令示例。"""

    await manager.send(
        f"{client_id} 你好！你发送的消息是: {message}",
        client_id,
    )
