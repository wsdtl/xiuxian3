import re

from launch.adapter.ws import ConnectionManager, WsMessageHandler


@WsMessageHandler.handler(cmd=re.compile(r"^你好呀$"), priority=20, block=False)
async def hello_user(
    client_id: str,
    match,
    manager: "ConnectionManager",
) -> None:
    """WebSocket 正则命令示例。

    block=False 表示本规则执行后，不阻断低优先级规则。
    发送 “你好呀” 时，会触发这个正则规则。
    """

    await manager.send(
        "你好呀！这是正则命令的回复。",
        client_id,
    )


@WsMessageHandler.handler(cmd=re.compile(r"温度"), priority=5, block=False)
async def match_anywhere(
    client_id: str,
    message: str,
    raw_message: str,
    manager: "ConnectionManager",
    match,
) -> None:
    """正则任意位置匹配示例。

    只要第一个空格前的内容里出现“温度”，就会触发。
    例如 “查询温度”、 “今天温度怎么样” 都可以命中。
    message 是命中“温度”后面的内容，raw_message 才是完整原文。
    """

    await manager.send(
        f"我在消息里找到了“温度”，触发后内容：{message}，完整原文：{raw_message}",
        client_id,
    )
