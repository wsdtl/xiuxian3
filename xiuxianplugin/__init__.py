import ast

from nonebot import logger
from nonebot import on_message
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageSegment

from .api import client

driver = get_driver()


@driver.on_shutdown
async def _():
    await client.close_all()


XiuXianGroup = ["123", "123"]

# 捕获所有消息事件
repeater = on_message(priority=1, block=False)


@repeater.handle()
async def _(event: GroupMessageEvent | PrivateMessageEvent):
    # 处理群消息
    if isinstance(event, GroupMessageEvent):
        if str(event.group_id) in XiuXianGroup:
            try:
                reply = await client.send(event.get_user_id(), event.get_message())
                if reply["code"] == 202:
                    if reply["type"] == "text":
                        await repeater.finish(reply["message"])
                    if reply["type"] == "image":
                        await repeater.finish(MessageSegment.image(f"base64://{reply['message']}"))
                    if reply["type"] == "markdown":
                        #  这里不是json格式 是{'key': 'value'} 疑似直接str(dict)的，要用ast解析
                        message = ast.literal_eval(reply['message'])
                        data = {
                            "markdown": {
                                "content": message['content'],
                                "keyboard": message['keyboard']
                            }
                        }
                        msg = MessageSegment("markdown", {"data": data})
                        await repeater.finish(msg)
                elif reply["code"] == 404:
                    logger.error(reply["message"])
            except Exception as e:
                pass

                # 处理私聊消息
    if isinstance(event, PrivateMessageEvent):
        try:
            reply = await client.send(event.get_user_id(), event.get_message())
            if reply["code"] == 202:
                if reply["type"] == "text":
                    await repeater.finish(reply["message"])
                if reply["type"] == "image":
                    await repeater.finish(MessageSegment.image(f"base64://{reply['message']}"))
                if reply["type"] == "markdown":
                    message = ast.literal_eval(reply['message'])
                    data = {
                        "markdown": {
                            "content": message['content'],
                            "keyboard": message['keyboard']
                        }
                    }
                    msg = MessageSegment("markdown", {"data": data})
                    await repeater.finish(msg)
                elif reply["code"] == 404:
                    logger.error(reply["message"])
        except Exception as e:
            pass
