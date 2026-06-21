# xiuxian3 安装说明

项目仓库：[wsdtl/xiuxian3](https://github.com/wsdtl/xiuxian3)

与本仓库 `nonebot_plugin_xiuxian_2_pmv` 的 **单体 NoneBot 插件** 不同，xiuxian3 为 **前后端分离**：

| 组件 | 说明 |
|------|------|
| `xiuxianserver` | FastAPI 修仙逻辑、SQLite、WebSocket `/ws/bot/{client_id}` |
| `xiuxianplugin` | NoneBot2 插件，通过 WebSocket 把 QQ/OneBot 消息转给服务端 |

安装脚本会克隆仓库，在本地生成：

- `{根目录}/server` — 服务端
- `{根目录}/bot` — NoneBot + `src/plugins/xiuxianplugin`
- `{根目录}/myenv` — 共用虚拟环境

并自动把插件 `api.py` 里的 `base_url` 改为 `ws://127.0.0.1:{SERVER_PORT}/ws/bot`。

## 脚本对照（与 pmv 安装方式一致）

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

管理命令（安装后）：`xiuxian3 start` / `start-server` / `start-bot` / `stop` / `update-deps`  
（无 root 时在 `~/.local/bin/xiuxian3`）

**启动顺序**：先服务端，再机器人。

## Termux

```bash
bash install_xiuxian3_termux.sh
```

管理命令：`~/bin/xiuxian3`（需 `~/bin` 在 PATH）

## Windows

双击或命令行运行 `install_xiuxian3.bat`，安装完成后：

- `run_server.bat` — 修仙服务端  
- `run_bot.bat` — NoneBot  
- `start_all.bat` — 开两个窗口依次启动  

需已安装 **Python 3.10+**、**Git**，并保证 `python` / `git` 在 PATH。

## 配置要点

- 服务端 `.env`：`SERVER_PORT`（默认 1234）、`ROUTER_MODULE_GROUPS=["auto"]`、`ROUTER_GROUPS=["修仙"]`（与上游封版记录一致）
- NoneBot `.env.dev`：`SUPERUSERS`、`PORT`（默认 8080，OneBot 反向 WS）
- 数据库：服务端目录下 SQLite（由项目自行管理），无需单独装 MySQL

## 与 pmv 脚本的差异

- pmv：下载 release `project.tar.gz`，逻辑在插件内  
- xiuxian3：`git clone` 全仓库，需 **两个进程**（server + bot）  
- pmv OneBot 地址：`/onebot/v11/ws`；xiuxian3 另需配置 **修仙 WS** 指向本机 `SERVER_PORT`

## 外网 / 内网穿透

若机器人与服务端不在同一机器，安装后需手动改 `bot/src/plugins/xiuxianplugin/api.py` 中 `base_url` 为可达的 `ws://主机:端口/ws/bot`，并放行 `SERVER_PORT`。