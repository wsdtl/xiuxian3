#!/usr/bin/env bash
# xiuxian3 一体化安装（Linux / Debian / Ubuntu 等，非 Termux）
# 项目：https://github.com/wsdtl/xiuxian3
# 架构：FastAPI 修仙服务端 (xiuxianserver) + NoneBot 桥接插件 (xiuxianplugin)

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

GITHUB_REPO="https://github.com/wsdtl/xiuxian3.git"
DEFAULT_ROOT_NAME="xiuxian3"
DEFAULT_SERVER_PORT="1234"
DEFAULT_NB_PORT="8080"

ui_print() {
    local color="$1"
    shift
    case "$color" in
        red) echo -e "${RED}$*${NC}" ;;
        green) echo -e "${GREEN}$*${NC}" ;;
        yellow) echo -e "${YELLOW}$*${NC}" ;;
        blue) echo -e "${BLUE}$*${NC}" ;;
        cyan) echo -e "${CYAN}$*${NC}" ;;
        white) echo -e "${WHITE}$*${NC}" ;;
        *) echo -e "$*" ;;
    esac
}

show_status() {
    if [[ "$2" == "success" ]]; then
        ui_print green "✓ $1 成功"
    else
        ui_print red "✗ $1 失败"
    fi
}

show_progress() { ui_print blue "正在 $1..."; }

read_or() {
    local var_name="$1" prompt="$2" default_value="$3" input=""
    if [[ -r /dev/tty ]] && { true < /dev/tty; } 2>/dev/null; then
        printf "%s (默认: %s): " "$prompt" "$default_value" > /dev/tty
        read -r input < /dev/tty || input=""
    else
        printf "%s (默认: %s): " "$prompt" "$default_value"
        read -r input || input=""
    fi
    [[ -z "$input" ]] && input="$default_value"
    printf -v "$var_name" '%s' "$input"
}

ensure_dir() { mkdir -p "$1"; }

detect_termux() {
    if [[ -d "${PREFIX:-}/bin" && -x "${PREFIX:-}/bin/pkg" && "$(uname -o 2>/dev/null)" == "Android" ]]; then
        ui_print yellow "检测到 Termux，请使用 install_xiuxian3_termux.sh"
        exit 127
    fi
}

usage() {
    cat <<EOF
用法: $0 [install|reinstall|update|update-deps] [安装根目录名或绝对路径]

默认安装到: \$HOME/$DEFAULT_ROOT_NAME
  server/  — FastAPI 修仙服务端
  bot/     — NoneBot2 + xiuxianplugin

示例:
  $0 install
  $0 update /opt/xiuxian3
EOF
}

show_main_menu() {
    ui_print green "========================================"
    ui_print green "xiuxian3 安装脚本 (Linux)"
    ui_print white "1. 安装  2. 重装  3. 更新  4. 更新依赖  5. 退出"
    ui_print green "========================================"
    local choice
    read_or choice "请输入编号" "1"
    case "$choice" in
        1) ACTION="install" ;;
        2) ACTION="reinstall" ;;
        3) ACTION="update" ;;
        4) ACTION="update-deps" ;;
        5) ui_print yellow "已退出."; exit 0 ;;
        *) ui_print red "无效选择"; exit 127 ;;
    esac
    read_or TARGET_INPUT "安装根目录（名或绝对路径）" "$DEFAULT_ROOT_NAME"
}

parse_args() {
    ACTION="install"
    TARGET_INPUT="$DEFAULT_ROOT_NAME"
    if [[ $# -eq 0 ]]; then
        show_main_menu
        return 0
    fi
    case "${1:-}" in
        install|reinstall|update|update-deps) ACTION="$1"; shift ;;
        -h|--help) usage; exit 0 ;;
    esac
    [[ $# -ge 1 ]] && TARGET_INPUT="$1"
}

resolve_paths() {
    if [[ "$TARGET_INPUT" == /* ]]; then
        ROOT="$TARGET_INPUT"
        PROJECT_NAME="$(basename "$ROOT")"
    else
        PROJECT_NAME="$TARGET_INPUT"
        ROOT="${HOME}/${PROJECT_NAME}"
    fi
    SERVER_DIR="$ROOT/server"
    BOT_DIR="$ROOT/bot"
    VENV_PATH="$ROOT/myenv"
    PLUGIN_PATH="$BOT_DIR/src/plugins/xiuxianplugin"
    API_PY="$PLUGIN_PATH/api.py"
}

install_apt_packages() {
    show_progress "检查系统依赖"
    if ! command -v python3 &>/dev/null; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-pip git curl screen
        else
            ui_print red "请先安装 python3、git、screen"
            return 1
        fi
    fi
    for cmd in git curl screen python3; do
        command -v "$cmd" &>/dev/null || { ui_print red "缺少命令: $cmd"; return 1; }
    done
    show_status "系统依赖" "success"
    return 0
}

clone_or_update_repo() {
    local tmp_clone="$ROOT/.src_xiuxian3"
    show_progress "获取 xiuxian3 源码"
    if [[ -d "$tmp_clone/.git" ]]; then
        git -C "$tmp_clone" pull --ff-only || return 1
    else
        rm -rf "$tmp_clone"
        git clone --depth 1 "$GITHUB_REPO" "$tmp_clone" || return 1
    fi
    show_status "获取源码" "success"
    return 0
}

sync_tree() {
    local tmp_clone="$ROOT/.src_xiuxian3"
    ensure_dir "$SERVER_DIR" "$BOT_DIR/src/plugins" "$ROOT/logs"
    if command -v rsync &>/dev/null; then
        rsync -a --delete \
            --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' \
            "$tmp_clone/xiuxianserver/" "$SERVER_DIR/"
    else
        find "$SERVER_DIR" -mindepth 1 -maxdepth 1 ! -name '.env' -exec rm -rf {} + 2>/dev/null || true
        cp -a "$tmp_clone/xiuxianserver/." "$SERVER_DIR/"
    fi
    rm -rf "$PLUGIN_PATH"
    cp -a "$tmp_clone/xiuxianplugin" "$PLUGIN_PATH"
    show_status "同步 server 与插件目录" "success"
}

write_server_env() {
    local port="$1"
    if [[ -f "$SERVER_DIR/.env" && "$ACTION" == "update" ]]; then
        ui_print yellow "保留已有 $SERVER_DIR/.env"
        return 0
    fi
    cat > "$SERVER_DIR/.env" <<EOF
PROJECT_NAME=xiuxian
PROJECT_DEBUG=False
PROJECT_TIMEZONE=Asia/Shanghai
PROJECT_DOMAIN=

SERVER_HOST=0.0.0.0
SERVER_PORT=$port

LOG_LEVEL=INFO
LOG_COLOR=auto

ROUTER_MODULE_GROUPS=["auto"]
ROUTER_MODULES=[]
ROUTER_FOLDERS=[]
ROUTER_GROUPS=["修仙"]
ROUTER_CHILD_FOLDERS=[]
EOF
    show_status "生成服务端 .env" "success"
}

patch_plugin_ws_url() {
    local port="$1"
    local ws_base="ws://127.0.0.1:${port}/ws/bot"
    if [[ ! -f "$API_PY" ]]; then
        ui_print red "未找到 $API_PY"
        return 1
    fi
    python3 - "$API_PY" "$ws_base" <<'PY'
import re, sys
path, ws = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
text, n = re.subn(
    r'(base_url:\s*str\s*=\s*)["\']ws://[^"\']+["\']',
    rf'\1"{ws}"',
    text,
    count=1,
)
if n != 1:
    raise SystemExit("未能改写 api.py 中的 base_url")
open(path, "w", encoding="utf-8").write(text)
PY
    show_status "配置插件 WebSocket 为 ${ws_base}" "success"
}

write_bot_pyproject() {
    cat > "$BOT_DIR/pyproject.toml" <<'EOF'
[project]
name = "xiuxian3-bot"
version = "0.1.0"
description = "xiuxian3 NoneBot bridge"
requires-python = ">=3.10, <4.0"
dependencies = [
    "nonebot2[fastapi,httpx,websockets,aiohttp]>=2.4.4",
    "nonebot-adapter-onebot>=2.4.6",
    "nonebot-adapter-qq>=1.7.1",
    "nonebot_plugin_apscheduler",
    "websockets>=12.0",
]

[tool.nonebot]
plugin_dirs = ["src/plugins"]
builtin_plugins = ["echo"]

[tool.nonebot.adapters]
nonebot-adapter-onebot = [
    { name = "OneBot V11", module_name = "nonebot.adapters.onebot.v11" }
]
"@local" = []
nonebot-adapter-qq = [{ name = "QQ", module_name = "nonebot.adapters.qq" }]

[tool.nonebot.plugins]
"@local" = []
EOF
}

write_bot_env() {
    local super="$1" nick="$2" port="$3"
    local su_list nick_list
    su_list=$(echo "$super" | sed -E 's/, */", "/g; s/^/"/; s/$/"/')
    nick_list=$(echo "$nick" | sed -E 's/, */", "/g; s/^/"/; s/$/"/')
    cat > "$BOT_DIR/.env" <<EOF
ENVIRONMENT=dev
DRIVER=~fastapi+~httpx+~websockets+~aiohttp
EOF
    cat > "$BOT_DIR/.env.dev" <<EOF
LOG_LEVEL=INFO
SUPERUSERS = [$su_list]
COMMAND_START = [""]
NICKNAME = [$nick_list]
DEBUG = False
HOST = 0.0.0.0
PORT = $port
EOF
    show_status "生成 NoneBot 配置" "success"
}

create_venv() {
    if [[ ! -d "$VENV_PATH" ]]; then
        show_progress "创建虚拟环境"
        python3 -m venv "$VENV_PATH" || return 1
    fi
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate" || return 1
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple >/dev/null 2>&1 || true
    pip install -U pip wheel >/dev/null 2>&1 || pip install -U pip
    show_status "虚拟环境" "success"
}

install_python_deps() {
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate"
    show_progress "安装服务端依赖"
    pip install -U -r "$SERVER_DIR/requirements.txt" || return 1
    show_progress "安装 NoneBot 与插件依赖"
    pip install -U "nb-cli" \
        "nonebot2[fastapi,httpx,websockets,aiohttp]" \
        "nonebot-adapter-onebot" "nonebot-adapter-qq" \
        "nonebot_plugin_apscheduler" "websockets>=12.0" || return 1
    show_status "Python 依赖" "success"
}

install_management_scripts() {
    local mgr
    if [[ -w /usr/local/bin ]] 2>/dev/null; then
        mgr="/usr/local/bin/${PROJECT_NAME}"
    else
        ensure_dir "$HOME/.local/bin"
        mgr="$HOME/.local/bin/${PROJECT_NAME}"
        ui_print yellow "管理命令: $mgr （请确保 ~/.local/bin 在 PATH 中）"
    fi

    cat > "${mgr}_server_start" <<EOF
#!/usr/bin/env bash
export TZ=Asia/Shanghai
source "$VENV_PATH/bin/activate"
cd "$SERVER_DIR" || exit 1
exec python main.py
EOF

    cat > "${mgr}_bot_start" <<EOF
#!/usr/bin/env bash
export TZ=Asia/Shanghai
source "$VENV_PATH/bin/activate"
cd "$BOT_DIR" || exit 1
exec nb run
EOF

    cat > "$mgr" <<EOF
#!/usr/bin/env bash
ROOT="$ROOT"
PROJECT_NAME="$PROJECT_NAME"
DIR="$ROOT"
SERVER_START="${mgr}_server_start"
BOT_START="${mgr}_bot_start"
VENV_PATH="$VENV_PATH"

screen_name() { echo "\${PROJECT_NAME}_\$1"; }

case "\${1:-start}" in
    start-server)
        sn=\$(screen_name server)
        if screen -list | grep -qF "\$sn"; then echo "服务端已在运行"; else
            screen -dmS "\$sn" -L -Logfile "\$DIR/logs/server.log" bash "\$SERVER_START"
            echo "已后台启动服务端"
        fi ;;
    start-bot)
        sn=\$(screen_name bot)
        if screen -list | grep -qF "\$sn"; then echo "机器人已在运行"; else
            screen -dmS "\$sn" -L -Logfile "\$DIR/logs/bot.log" bash "\$BOT_START"
            echo "已后台启动机器人"
        fi ;;
    start)
        "\$0" start-server
        sleep 2
        "\$0" start-bot ;;
    stop-server)
        screen -X -S "\$(screen_name server)" quit 2>/dev/null && echo "服务端已停止" || echo "服务端未运行" ;;
    stop-bot)
        screen -X -S "\$(screen_name bot)" quit 2>/dev/null && echo "机器人已停止" || echo "机器人未运行" ;;
    stop)
        "\$0" stop-bot
        "\$0" stop-server ;;
    status-server) screen -r "\$(screen_name server)" ;;
    status-bot) screen -r "\$(screen_name bot)" ;;
    update-deps)
        source "\$VENV_PATH/bin/activate"
        pip install -U -r "\$ROOT/server/requirements.txt"
        pip install -U nb-cli "nonebot2[fastapi,httpx,websockets,aiohttp]" nonebot-adapter-onebot nonebot-adapter-qq nonebot_plugin_apscheduler websockets
        ;;
    *)
        echo "用法: \$PROJECT_NAME {start|start-server|start-bot|stop|stop-server|stop-bot|status-server|status-bot|update-deps}"
        ;;
esac
EOF

    chmod +x "$mgr" "${mgr}_server_start" "${mgr}_bot_start"
    show_status "管理脚本 $mgr" "success"
}

final_message() {
    local sp nb
    sp=$(grep -E '^SERVER_PORT=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2)
    nb=$(grep -E '^PORT *= *' "$BOT_DIR/.env.dev" 2>/dev/null | sed -E 's/.*= *//')
    [[ -z "$sp" ]] && sp="$DEFAULT_SERVER_PORT"
    [[ -z "$nb" ]] && nb="$DEFAULT_NB_PORT"
    ui_print green "========================================"
    ui_print green "✓ ${ACTION} 完成"
    ui_print white "安装根目录: $ROOT"
    ui_print white "修仙服务端: http://127.0.0.1:${sp}"
    ui_print white "修仙 WebSocket: ws://127.0.0.1:${sp}/ws/bot/{client_id}"
    ui_print white "NoneBot OneBot11: ws://127.0.0.1:${nb}/onebot/v11/ws"
    ui_print cyan "启动顺序: ${PROJECT_NAME} start-server → ${PROJECT_NAME} start-bot（或 ${PROJECT_NAME} start）"
    ui_print green "========================================"
}

main() {
    detect_termux
    parse_args "$@"
    resolve_paths

    ui_print cyan "模式: $ACTION | 目录: $ROOT"

    if [[ "$ACTION" == "reinstall" ]]; then
        read_or c "删除 $ROOT 请输入 YES" "NO"
        [[ "$c" == "YES" ]] || exit 0
        rm -rf "$ROOT"
        ACTION="install"
    fi

    if [[ "$ACTION" == "update-deps" ]]; then
        [[ -d "$VENV_PATH" ]] || { ui_print red "未安装，请先 install"; exit 127; }
        create_venv && install_python_deps && final_message
        exit 0
    fi

    if [[ "$ACTION" == "install" && -f "$SERVER_DIR/main.py" ]]; then
        ui_print red "目录已存在，请用 update 或删除后重装"
        exit 127
    fi

    if [[ "$ACTION" == "update" && ! -f "$SERVER_DIR/main.py" ]]; then
        ui_print yellow "未检测到安装，切换为 install"
        ACTION="install"
    fi

    install_apt_packages || exit 127
    ensure_dir "$ROOT"
    clone_or_update_repo || exit 127
    sync_tree || exit 127

    if [[ "$ACTION" == "install" ]]; then
        read_or SERVER_PORT "修仙服务端端口 SERVER_PORT" "$DEFAULT_SERVER_PORT"
        read_or SUPERUSERS "主人 QQ（逗号分隔）" "123456"
        read_or NICKNAME "机器人昵称（逗号分隔）" "修仙助手"
        read_or NB_PORT "NoneBot 端口" "$DEFAULT_NB_PORT"
        write_bot_env "$SUPERUSERS" "$NICKNAME" "$NB_PORT"
        write_bot_pyproject
        install_management_scripts
    else
        SERVER_PORT=$(grep -E '^SERVER_PORT=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2)
        [[ -z "$SERVER_PORT" ]] && SERVER_PORT="$DEFAULT_SERVER_PORT"
        [[ -f "$BOT_DIR/pyproject.toml" ]] || write_bot_pyproject
    fi

    write_server_env "$SERVER_PORT"
    patch_plugin_ws_url "$SERVER_PORT" || exit 127

    create_venv || exit 127
    install_python_deps || exit 127

    final_message
}

main "$@"