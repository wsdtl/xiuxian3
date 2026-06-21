# 修仙项目

本仓库包含修仙后端和机器人转发插件：

```text
xiuxianserver/    FastAPI + WebSocket 修仙后端
xiuxianplugin/    NoneBot 机器人转发插件
```

日常功能开发以 `xiuxianserver/修仙` 业务组件为主。排查问题时需要看完整项目链路，包括后端、框架层和插件；默认不修改 `xiuxianplugin`，也不修改 `xiuxianserver/launch`、`auto`、Adapter、生命周期和路由加载等框架层代码。

项目和框架维护边界见 `xiuxianserver/开发约束.md`；修仙组件开发约束见 `xiuxianserver/修仙/开发约束.md`。服务端玩法、命令和回复规则以代码为准，组件说明 Markdown 只记录业务边界和扩展约束。

![项目Logo](help.png)

## 一键安装（推荐）

本仓库提供一键脚本，自动完成：**克隆源码 → 部署修仙服务端 + NoneBot 机器人 → 虚拟环境与依赖 → 生成配置与启动命令**。  
安装后需 **先启动服务端，再启动机器人**（两个进程）。

| 系统 | 脚本 | 默认安装位置 |
|------|------|----------------|
| Linux（Debian/Ubuntu 等） | `install_xiuxian3.sh` | `~/xiuxian3` |
| Termux（Android） | `install_xiuxian3_termux.sh` | `~/xiuxian3` |
| Windows | `install_xiuxian3.bat` | `%USERPROFILE%\xiuxian3` |

### 快速开始

**Linux**

```bash
git clone --depth 1 https://github.com/wsdtl/xiuxian3.git
cd xiuxian3
chmod +x install_xiuxian3.sh
./install_xiuxian3.sh          # 交互菜单：安装 / 更新 / 更新依赖
# 或
./install_xiuxian3.sh install  # 非交互安装
```

安装完成后使用管理命令（项目名默认为 `xiuxian3`）：

```text
xiuxian3 start          # 先起服务端，再起机器人
xiuxian3 start-server   # 仅修仙后端
xiuxian3 start-bot      # 仅 NoneBot
xiuxian3 stop           # 停止全部
xiuxian3 update-deps    # 更新 Python 依赖
```

无 root 时管理命令可能在 `~/.local/bin/xiuxian3`，请保证该目录在 `PATH` 中。

**Termux**

```bash
git clone --depth 1 https://github.com/wsdtl/xiuxian3.git
cd xiuxian3
bash install_xiuxian3_termux.sh
```

管理命令：`~/bin/xiuxian3`（需 `~/bin` 在 PATH）。

**Windows**

1. 安装 [Python 3.10+](https://www.python.org/) 与 [Git](https://git-scm.com/)，并勾选加入 PATH。  
2. 克隆本仓库后双击或运行 `install_xiuxian3.bat`。  
3. 安装完成后使用安装目录下的 `start_all.bat`，或分别运行 `run_server.bat`、`run_bot.bat`。

### 安装后的目录结构

```text
xiuxian3/                 # 安装根目录（可自定义）
├── server/               # FastAPI 修仙服务端（来自 xiuxianserver）
├── bot/                  # NoneBot2 + xiuxianplugin
├── myenv/                # Python 虚拟环境
└── logs/                 # 运行日志
```

脚本会自动将插件 `xiuxianplugin/api.py` 中的 WebSocket 地址指向本机服务端（默认 `ws://127.0.0.1:1234/ws/bot`），并生成服务端 `.env`、NoneBot `.env.dev`。

### 连接 QQ / OneBot

- **OneBot 反向 WS**（go-cqhttp、LLOneBot 等）：`ws://127.0.0.1:8080/onebot/v11/ws`（端口以安装时填写的 NoneBot 端口为准）  
- **修仙逻辑**：由机器人插件经 WebSocket 连接本地服务端，一般无需单独配置。

更详细的说明、更新与排错见仓库内 [INSTALL_XIUXIAN3.md](INSTALL_XIUXIAN3.md)。
