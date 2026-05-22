# xiuxianserver

FastAPI 后端服务，包含 HTTP 接口和 WebSocket 消息适配器。

## 运行

本项目使用 Miniconda 的 `ws` 环境：

```sh
conda run -n ws python main.py
```

默认监听：

```text
http://127.0.0.1:7001
```

## 系统配置

可变化的系统配置集中放在项目根目录的 `.env` 文件里。
本地开发可以复制 `.env.example` 为 `.env`，项目启动时会自动读取。
项目配置入口只有 `.env` 一个。
`.env` 只建议放经常变化的配置和自定义配置。
日志这类系统默认配置已经写在 [launch/config.py](C:/Users/16841/Desktop/xiuxianserver/launch/config.py:1)，非必要不用写进 `.env`。

```powershell
Copy-Item .env.example .env
```

其他模块需要读取配置时，直接导入已经实例化好的 `config`：

```python
from launch import config

print(config.project.name)
print(config.project.debug)
print(config.log.level)
print(config.router.modules)
print(config.zdy1)
```

项目基础配置：

```text
APP_NAME=xiuxianserver
APP_DEBUG=false
```

对应读取方式：

```python
from launch import config

app_name = config.project.name
debug = config.project.debug
```

自定义参数可以直接从 `config` 读取。
例如 `.env` 里新增：

```text
zdy1=hello
```

代码里读取：

```python
from launch import config

value = config.zdy1
```

如果自定义配置名不是合法 Python 属性名，可以从 `config.custom` 读取：

```text
MY-TOKEN=123456
```

```python
from launch import config

token = config.get("MY-TOKEN", "")
```

`config.get(...)` 是读取自定义配置最稳的方式。
像 `MY-TOKEN`、`abc.def`、`1name` 这种名字不会影响项目启动，但不能用点语法读取，直接用原始名字读取即可：

```python
config.get("MY-TOKEN")
config.get("abc.def")
config.get("1name")
```

长期使用、需要明确类型的参数，推荐像 `ProjectConfig` / `LogConfig` 一样写进 [launch/config.py](C:/Users/16841/Desktop/xiuxianserver/launch/config.py:1)，这样类型和用途更清楚。

模块 / 路由加载配置：

```text
APP_MODULE_GROUPS=["auto"]
APP_MODULES=["src.ws"]
APP_ROUTER_FOLDERS=["src.室温监控"]
APP_ROUTER_GROUPS=[]
APP_ROUTER_CHILD_FOLDERS=[]
```

RouterConfig 必须写成列表，不再使用逗号分隔。
也就是说，多项配置这样写：

```text
APP_MODULES=["src.ws"]
```

带 `APIRouter` 的 HTTP 模块会在应用创建阶段注册，因此 `/docs` 和 `/openapi.json` 可以直接显示所有 `@router.get(...)`、`@router.post(...)` 等接口。
没有手动写 `tags` 的模块，会按模块名自动分类。
例如：

```text
APP_ROUTER_FOLDERS=["src.室温监控"]
```

会在 `/docs` 里显示为 `室温监控` 分类。

含义：

```text
APP_MODULE_GROUPS        加载某个目录下的所有子模块，例如 auto -> auto.cfg
APP_MODULES              加载普通模块，不要求模块里有 router
APP_ROUTER_FOLDERS       加载带 router 的模块
APP_ROUTER_GROUPS        加载自身带 router、子目录为普通模块的模块组
APP_ROUTER_CHILD_FOLDERS 加载某个目录下所有带 router 的子模块
```

## 日志配置

日志统一在 `launch/log.py` 配置，项目代码推荐这样导入：

```python
from launch import logger, C
```

普通日志直接写：

```python
logger.debug("调试信息")
logger.info("普通信息")
logger.success("成功信息")
logger.warning("警告信息")
logger.error("错误信息")
```

彩色日志需要使用 `logger.opt(colors=True)`。
推荐用 `C` 生成颜色片段，不要在业务代码里到处手写 `<green>...</green>`：

```python
logger.opt(colors=True).success(
    f"{C.ok('模块加载成功')} {C.kv('module', module_name)}"
)

logger.opt(colors=True).warning(
    f"{C.warn('发送失败')} {C.kv('path', path)}"
)

logger.opt(colors=True).error(
    f"{C.fail('任务异常')} {C.kv('task', task_id)}"
)
```

如果一条日志太长，推荐用 `C.join(...)`。
逗号写在 `C.join(...)` 里面，方便格式化器换行；`logger.info(...)` 仍然只接收一个 message。

```python
logger.opt(colors=True).info(
    C.join(
        C.warn("室温监控历史数据已更新"),
        C.kv("time", datetime.now()),
        C.kv("count", len(historydata)),
    )
)
```

Loguru 原本的 `{}` 格式化写法也可以继续用：

```python
logger.info("用户 {} 登录成功", user_id)
```

常用颜色工具：

```python
C.black(text)
C.red(text)
C.green(text)
C.yellow(text)
C.blue(text)
C.magenta(text)
C.cyan(text)
C.white(text)
```

常用语义工具：

```python
C.ok(text)       # 成功，绿色加粗
C.warn(text)     # 警告，黄色加粗
C.fail(text)     # 失败，红色加粗
C.key(text)      # 字段名，青色
C.value(text)    # 字段值，黄色
C.kv(key, value) # key=value 彩色片段
C.msg(text)      # 普通消息内容
```

记录异常时，把异常对象交给 `logger.opt(exception=exc)`：

```python
try:
    ...
except Exception as exc:
    logger.opt(colors=True, exception=exc).error(
        f"{C.fail('处理失败')} {C.kv('module', module_name)}"
    )
```

日志配置有默认值，默认不用写进 `.env`。
确实需要变化时，再把对应 `LOG_*` 写进 `.env` 覆盖。

例如调整日志级别：

```text
LOG_LEVEL=DEBUG
```

例如调整控制台颜色：

```text
# 默认，终端支持就显示颜色，否则显示纯文本
LOG_COLOR=auto

# 强制显示颜色
LOG_COLOR=true

# 强制关闭颜色
LOG_COLOR=false
```

其他可覆盖的日志配置：

```text
LOG_DIR=launch/log
LOG_FILE=launch/log/runserver.log
LOG_ROTATION=12:00
LOG_RETENTION=14 days
LOG_COMPRESSION=zip
```

控制台日志会显示颜色，文件日志会写入纯文本：

```text
launch/log/runserver.log
```

文件日志每天 12:00 轮转，保留 14 天，旧日志会压缩。
`uvicorn`、`uvicorn.error`、`uvicorn.access` 的标准 logging 日志也会转发到同一套 loguru 配置里。

## WebSocket 连接

连接地址：

```text
ws://127.0.0.1:7001/ws/bot/{client_id}
```

示例：

```text
ws://127.0.0.1:7001/ws/bot/user001
```

如果页面是 HTTPS，线上连接需要使用 `wss://`：

```text
wss://你的域名/ws/bot/user001
```

导入 WebSocket 分发器：

```python
from launch.adapter.ws import WsMessageHandler
```

说明：当前连接模型是“一个 `client_id` 只保留最后一条连接”。
同一个用户重复连接时，新连接会接管身份，旧连接会被关闭。
业务里调用 `manager.send(message, client_id)` 会发送给这个 `client_id` 当前保留的连接。
调用 `manager.send_all(message)` 会广播给所有在线 `client_id` 的当前连接。
旧连接关闭时会带上原因：`同 client_id 新连接已接管`。

## WebSocket 消息格式

WS 通讯统一使用三个字段：

```json
{
  "code": 202,
  "type": "text",
  "message": "你好 hello"
}
```

字段含义：

- `code`: `202` 表示正常，`404` 表示异常。
- `type`: 自定义消息类型，默认用 `text`，客户端可自行判断。
- `message`: 消息文本。

字段顺序固定为 `code -> type -> message`。
`code` 兼容数字和字符串，例如 `202`、`"202"`、`404`、`"404"`。

不使用业务层 `ping/pong` 心跳。

连接是否失效交给 WebSocket/TCP 层和读写异常处理：

- 客户端主动关闭时，服务端会收到断开事件并清理连接。
- 服务端发送失败时，会清理对应连接。
- 静默断网不会立刻发现，通常会在下一次读写时发现。

## WebSocket 命令注册

精确命令：

```python
@WsMessageHandler.handler(cmd="你好", priority=10, block=False)
async def hello(client_id, message, manager):
    await manager.send({"message": "回复触发者"}, client_id)
```

正则命令：

```python
@WsMessageHandler.handler(
    cmd=re.compile(r"^你好(?P<name>\S+)$"),
    priority=20,
    block=True,
)
```

正则使用 `search()`，可以匹配文本里的任意位置。
如果只想从开头匹配，就在正则里写 `^`：

```python
@WsMessageHandler.handler(cmd=re.compile(r"温度"))
async def keyword(client_id, raw_message, manager):
    await manager.send(f"消息里出现了温度: {raw_message}", client_id)
```

分发规则：

- 精确匹配和正则匹配没有天然高低，只看 `priority`。
- `priority` 数字越大越先执行。
- 同一优先级的所有匹配都会执行。
- `block=True` 执行后，会阻断更低优先级的规则继续执行。
- 有固定文字前缀的正则会走快速索引；没有固定前缀的正则也能注册，会走兜底匹配。

## WebSocket 消息传播流程

一条消息从客户端到业务函数，大致是这样走的：

```text
客户端 JSON 文本
-> websocket_endpoint 接收文本
-> _loads_message 解析 JSON
-> _dispatch_message 判断 code
-> code == 202 时创建后台任务
-> 对应驱动的 MessageHandler.dispatch 进入命令分发
-> 拆出第一个空格前的 cmd
-> 找到所有精确命令和正则命令命中项
-> 按 priority 从高到低执行
-> block=True 时阻断更低优先级
-> 业务函数用 manager.send(..., client_id) 回复客户端
```

业务函数中推荐使用：

```python
await manager.send(message, client_id)
```

如果同一个 `client_id` 重复连接，只有最后一次连接会收到消息。
可查看 [replace_connection.py](C:/Users/16841/Desktop/xiuxianserver/src/ws/replace_connection.py:1) 示例。

广播给所有在线客户端：

```python
await manager.send_all(message)
```

当前业务函数默认只应期待“一条发送对应一条主要回复”。
如果一个消息同时命中多个同优先级规则，服务端会逐条发送；像 `ws_test.py` 这种测试客户端只等待第一条回复。

`manager.send(...)` 和 `manager.send_all(...)` 会自动把内容整理成：

```json
{
  "code": 202,
  "type": "text",
  "message": "文本内容"
}
```

发送故障消息时使用：

```python
await manager.send({"code": 404, "type": "text", "message": "错误原因"}, client_id)
```

## 前端连接示例

```js
const clientId = "user001";
const ws = new WebSocket(`ws://127.0.0.1:7001/ws/bot/${clientId}`);

ws.onopen = () => {
  ws.send(JSON.stringify({
    code: 202,
    type: "text",
    message: "你好 hello"
  }));

  ws.send(JSON.stringify({
    code: 202,
    type: "text",
    message: "你好管委会-731"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("收到服务端消息:", data);
};

ws.onclose = () => {
  console.log("WebSocket 已断开");
};

ws.onerror = (error) => {
  console.error("WebSocket 错误:", error);
};
```
