# xiuxian3 安装说明

项目仓库：[wsdtl/xiuxian3](https://github.com/wsdtl/xiuxian3)

xiuxian3 当前是 **修仙服务端 + 通信适配器** 的结构：

| 组件 | 说明 |
|------|------|
| `xiuxianserver` | FastAPI 修仙逻辑、SQLite、静态资源、内置 QQ webhook / WebSocket 适配器 |
| `xiuxianplugin` | 可选 NoneBot2 桥接插件，通过 WebSocket 把 OneBot 消息转给服务端 |

安装脚本会克隆仓库，并在安装目录生成：

- `server`：修仙服务端
- `bot`：NoneBot + `src/plugins/xiuxianplugin`
- `myenv`：共用 Python 虚拟环境
- `logs`：Linux / Termux 后台运行日志

脚本会自动把 `xiuxianplugin/api.py` 的 `base_url` 改成 `ws://127.0.0.1:{SERVER_PORT}/ws/bot`。

## 运行方式

### QQ 官方机器人 webhook

推荐只启动服务端：

```bash
xiuxian3 start-server
```

开放平台回调地址填写：

```text
https://你的域名或公网地址:8443/qq/events
```

前提是外部能访问这个 HTTPS 地址。若由服务端自己提供 HTTPS，需要在 `server/.env` 填写证书：

```env
SERVER_PORT=8443
SERVER_SSL_CERTFILE=certs/fullchain.pem
SERVER_SSL_KEYFILE=certs/privkey.pem
QQ_EVENT_PATH=/qq/events
QQ_BOT_APP_ID=
QQ_BOT_SECRET=
```

`QQ_BOT_SECRET` 用于开放平台回调验证和 OpenAPI 鉴权，不需要再单独配置旧式 AccessToken。

### OneBot / NoneBot 桥接

需要同时启动服务端和机器人桥接：

```bash
xiuxian3 start-server
xiuxian3 start-bot
```

OneBot 反向 WebSocket 地址仍是：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

## 脚本对照

| 环境 | 脚本 |
|------|------|
| Debian / Ubuntu / 一般 Linux | `install_xiuxian3.sh` |
| Termux (Android) | `install_xiuxian3_termux.sh` |
| Windows | `install_xiuxian3.bat` |

## Linux

```bash
chmod +x install_xiuxian3.sh
./install_xiuxian3.sh          # 交互菜单
./install_xiuxian3.sh install  # 直接安装到 ~/xiuxian3
./install_xiuxian3.sh update
```

安装后会生成管理命令：

```bash
xiuxian3 start-server
xiuxian3 start-bot
xiuxian3 start
xiuxian3 stop
xiuxian3 update-deps
```

无 root 权限时，管理命令会放在 `~/.local/bin/xiuxian3`，请确认 `~/.local/bin` 已加入 `PATH`。

## Termux

```bash
bash install_xiuxian3_termux.sh
```

管理命令默认生成在：

```text
~/bin/xiuxian3
```

请确认 `~/bin` 已加入 `PATH`。

## Windows

双击或命令行运行：

```bat
install_xiuxian3.bat
```

安装完成后会在安装目录生成：

- `run_server.bat`：启动修仙服务端
- `run_bot.bat`：启动 NoneBot 桥接
- `start_all.bat`：开两个窗口启动服务端和桥接

Windows 需要提前安装 **Python 3.10+** 和 **Git**，并保证 `python` / `git` 在 PATH。

## 服务端配置

新安装时脚本会生成 `server/.env`。更新已有安装时会保留旧 `.env`，只补充缺失的新配置键，不会覆盖你的证书、端口或机器人密钥。

常用字段：

| 字段 | 说明 |
|------|------|
| `SERVER_PORT` | 服务端监听端口，脚本默认 `8443` |
| `SERVER_SSL_CERTFILE` | HTTPS 证书路径，可写相对 `server` 的路径，如 `certs/fullchain.pem` |
| `SERVER_SSL_KEYFILE` | HTTPS 私钥路径 |
| `PROJECT_DOMAIN` | 生成公开链接使用的域名或完整基地址，如 `https://example.com:8443` |
| `ADAPTERS` | 启用适配器，默认 `["qq","ws"]` |
| `QQ_EVENT_PATH` | QQ webhook 路径，默认 `/qq/events` |
| `QQ_BOT_APP_ID` | QQ 机器人 AppID |
| `QQ_BOT_SECRET` | QQ 机器人 Secret |
| `ROUTER_MODULE_GROUPS` | 默认 `["auto"]` |
| `ROUTER_GROUPS` | 默认 `["修仙"]` |

如果只使用 NoneBot / OneBot 桥接，可以把 `ADAPTERS` 改成：

```env
ADAPTERS=["ws"]
```

如果同时使用 QQ webhook 和 WebSocket，保持默认即可。

## 外网访问

QQ 开放平台后台只接受 HTTPS 回调。常见做法有两种：

1. 服务端直接启用 HTTPS，并让公网端口透传到 `SERVER_PORT`。
2. 用 Nginx、frp、云代理等在外层终止 HTTPS，再转发到本地服务端。

如果 HTTPS 在外层终止，`SERVER_SSL_CERTFILE` / `SERVER_SSL_KEYFILE` 可以留空，但 `PROJECT_DOMAIN` 建议写成外部真实地址，例如：

```env
PROJECT_DOMAIN=https://bot.example.com
```

如果机器人桥接和服务端不在同一台机器，还需要手动把 `bot/src/plugins/xiuxianplugin/api.py` 的 `base_url` 改成可访问的：

```text
ws://服务端地址:端口/ws/bot
```
