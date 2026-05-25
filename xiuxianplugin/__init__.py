import ast
from pathlib import Path

from nonebot import logger
from nonebot import on_message
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment as MessageSegmentOneBotV11

try:
    from nonebot.adapters.qq import (
        GroupAtMessageCreateEvent,
        GroupMessageCreateEvent,
        C2CMessageCreateEvent)
    from nonebot.adapters.qq import MessageSegment as MessageSegmentQQ

    ENABLE_ADAPTER_QQ = True
except ImportError:
    logger.error("没有成功加载QQ官方机器人适配器，尝试前往安装nonebot-adapter-qq")
    ENABLE_ADAPTER_QQ = False
    GroupAtMessageCreateEvent = None
    GroupMessageCreateEvent = None
    C2CMessageCreateEvent = None
    MessageSegmentQQ = None

from .api import client

driver = get_driver()


@driver.on_shutdown
async def _():
    await client.close_all()


XiuXianGroup = []
"""使用范围（群聊）"""
ReverseXiuXianGroup = False
"""反转使用范围为黑名单范围，其余开放"""
if not XiuXianGroup:
    logger.warning(f"注意: 你没有配置群聊的使用范围，请前往{Path(__file__)}下配置群聊使用范围XiuXianGroup")

# 捕获所有消息事件
repeater = on_message(priority=1, block=False)


@repeater.handle()
async def _(
        event: GroupMessageEvent | PrivateMessageEvent | GroupAtMessageCreateEvent | C2CMessageCreateEvent | GroupMessageCreateEvent):
    # 处理群消息
    if isinstance(event, GroupMessageEvent):
        if (str(event.group_id) in XiuXianGroup) ^ ReverseXiuXianGroup:
            try:
                reply = await client.send(event.get_user_id(), event.get_message())
                await handle_ws_reply_onebot_v11(reply, repeater)
            except Exception as e:
                pass
    # 处理来自官方机器人的群消息
    if ENABLE_ADAPTER_QQ and isinstance(event, GroupAtMessageCreateEvent | GroupMessageCreateEvent):
        if (str(event.group_openid) in XiuXianGroup) ^ ReverseXiuXianGroup:
            try:
                reply = await client.send(event.get_user_id(), event.get_message())
                await handle_ws_reply_qq(reply, repeater)
            except Exception as e:
                pass

    # 处理私聊消息
    if isinstance(event, PrivateMessageEvent):
        try:
            reply = await client.send(event.get_user_id(), event.get_message())
            await handle_ws_reply_onebot_v11(reply, repeater)
        except Exception as e:
            pass
    # 处理来自官方机器人的私聊消息
    if ENABLE_ADAPTER_QQ and isinstance(event, C2CMessageCreateEvent):
        try:
            reply = await client.send(event.get_user_id(), event.get_message())
            await handle_ws_reply_qq(reply, repeater)
        except Exception as e:
            pass


async def handle_ws_reply_qq(reply, matcher):
    if reply["code"] == 202:
        if reply["type"] == "text":
            await matcher.finish(reply["message"])
        if reply["type"] == "image":
            await matcher.finish(MessageSegmentQQ.image(f"base64://{reply['message']}"))
        if reply["type"] == "markdown":
            #  这里不是json格式 是{'key': 'value'} 疑似直接str(dict)的，要用ast解析
            message = ast.literal_eval(reply['message'])
            msg = MessageSegmentQQ.markdown(message['content']) + MessageSegmentQQ.keyboard(message['keyboard'])
            await matcher.finish(msg)
    elif reply["code"] == 404:
        logger.error(reply["message"])


async def handle_ws_reply_onebot_v11(reply, matcher):
    if reply["code"] == 202:
        if reply["type"] == "text":
            await matcher.finish(reply["message"])
        if reply["type"] == "image":
            await matcher.finish(MessageSegmentOneBotV11.image(f"base64://{reply['message']}"))
        if reply["type"] == "markdown":
            message = ast.literal_eval(reply['message'])
            data = {
                "markdown": {
                    "content": message['content'],
                    "keyboard": message['keyboard']
                }
            }
            msg = MessageSegmentOneBotV11("markdown", {"data": data})
            await matcher.finish(msg)
        elif reply["code"] == 404:
            logger.error(reply["message"])
