#!/data/data/com.termux/files/usr/bin/bash
# xiuxian3 安装脚本（Termux / Android）
# 项目：https://github.com/wsdtl/xiuxian3

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
DEFAULT_SERVER_PORT="8443"
DEFAULT_NB_PORT="8080"
DEFAULT_ADAPTERS="qq,ws"
DEFAULT_QQ_EVENT_PATH="/qq/events"

TERMUX_HOME="${HOME:-/data/data/com.termux/files/home}"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"

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

ensure_dir() { mkdir -p "$@"; }

make_adapter_list() {
    local raw="${1// /}" item sep="" out="["
    local -a items=()
    IFS=',' read -r -a items <<< "$raw"
    for item in "${items[@]}"; do
        [[ -n "$item" ]] || continue
        out="${out}${sep}\"${item}\""
        sep=","
    done
    if [[ "$out" == "[" ]]; then
        out="[\"qq\",\"ws\"]"
    else
        out="${out}]"
    fi
    printf '%s' "$out"
}

detect_termux() {
    if [[ ! -x "$TERMUX_PREFIX/bin/pkg" ]]; then
        ui_print red "未检测到 Termux，请使用 install_xiuxian3.sh（Linux）"
        exit 127
    fi
}

usage() {
    cat <<EOF
用法: $0 [install|reinstall|update|update-deps] [目录名或绝对路径]

默认: $TERMUX_HOME/$DEFAULT_ROOT_NAME
EOF
}

show_main_menu() {
    ui_print green "========================================"
    ui_print green "xiuxian3 安装 (Termux)"
    ui_print white "1.安装 2.重装 3.更新 4.更新依赖 5.退出"
    ui_print green "========================================"
    local choice
    read_or choice "编号" "1"
    case "$choice" in
        1) ACTION="install" ;;
        2) ACTION="reinstall" ;;
        3) ACTION="update" ;;
        4) ACTION="update-deps" ;;
        5) exit 0 ;;
        *) exit 127 ;;
    esac
    read_or TARGET_INPUT "安装目录" "$DEFAULT_ROOT_NAME"
}

parse_args() {
    ACTION="install"
    TARGET_INPUT="$DEFAULT_ROOT_NAME"
    if [[ $# -eq 0 ]]; then show_main_menu; return 0; fi
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
        ROOT="$TERMUX_HOME/$PROJECT_NAME"
    fi
    SERVER_DIR="$ROOT/server"
    BOT_DIR="$ROOT/bot"
    VENV_PATH="$ROOT/myenv"
    PLUGIN_PATH="$BOT_DIR/src/plugins/xiuxianplugin"
    API_PY="$PLUGIN_PATH/api.py"
    BIN_DIR="$TERMUX_HOME/bin"
}

install_termux_packages() {
    show_progress "安装 Termux 包"
    pkg install -y \
        bash curl wget git python screen tar unzip \
        proot-distro 2>/dev/null || true
    pkg install -y bash curl wget git python screen tar unzip procps findutils grep sed coreutils
    show_status "Termux 依赖" "success"
}

clone_or_update_repo() {
    local tmp_clone="$ROOT/.src_xiuxian3"
    show_progress "克隆/更新 xiuxian3"
    if [[ -d "$tmp_clone/.git" ]]; then
        git -C "$tmp_clone" pull --ff-only || return 1
    else
        rm -rf "$tmp_clone"
        git clone --depth 1 "$GITHUB_REPO" "$tmp_clone" || return 1
    fi
    show_status "源码" "success"
}

sync_tree() {
    local tmp_clone="$ROOT/.src_xiuxian3"
    ensure_dir "$SERVER_DIR" "$BOT_DIR/src/plugins" "$ROOT/logs"
    find "$SERVER_DIR" -mindepth 1 -maxdepth 1 ! -name '.env' -exec rm -rf {} + 2>/dev/null || true
    cp -a "$tmp_clone/xiuxianserver/." "$SERVER_DIR/"
    rm -rf "$PLUGIN_PATH"
    cp -a "$tmp_clone/xiuxianplugin" "$PLUGIN_PATH"
    show_status "同步目录" "success"
}

write_server_env() {
    local port="$1"
    local project_domain="${PROJECT_DOMAIN:-}"
    local ssl_certfile="${SERVER_SSL_CERTFILE:-}"
    local ssl_keyfile="${SERVER_SSL_KEYFILE:-}"
    local adapters_list="${ADAPTERS_LIST:-[\"qq\",\"ws\"]}"
    local qq_event_path="${QQ_EVENT_PATH:-$DEFAULT_QQ_EVENT_PATH}"
    local qq_app_id="${QQ_BOT_APP_ID:-}"
    local qq_secret="${QQ_BOT_SECRET:-}"
    if [[ -f "$SERVER_DIR/.env" && "$ACTION" == "update" ]]; then
        ui_print yellow "保留 $SERVER_DIR/.env"
        return 0
    fi
    cat > "$SERVER_DIR/.env" <<EOF
PROJECT_NAME=xiuxian
PROJECT_DEBUG=False
PROJECT_TIMEZONE=Asia/Shanghai
PROJECT_DOMAIN=$project_domain

SERVER_HOST=0.0.0.0
SERVER_PORT=$port
SERVER_RELOAD=False
SERVER_SSL_CERTFILE=$ssl_certfile
SERVER_SSL_KEYFILE=$ssl_keyfile

LOG_LEVEL=INFO
LOG_COLOR=auto

ADAPTERS=$adapters_list

QQ_EVENT_PATH=$qq_event_path
QQ_BOT_APP_ID=$qq_app_id
QQ_BOT_SECRET=$qq_secret

ROUTER_MODULE_GROUPS=["auto"]
ROUTER_MODULES=[]
ROUTER_FOLDERS=[]
ROUTER_GROUPS=["修仙"]
ROUTER_CHILD_FOLDERS=[]
EOF
    show_status "服务端 .env" "success"
}

append_env_if_missing() {
    local key="$1" value="$2"
    grep -qE "^${key}=" "$SERVER_DIR/.env" 2>/dev/null || printf '%s=%s\n' "$key" "$value" >> "$SERVER_DIR/.env"
}

ensure_server_env_defaults() {
    [[ -f "$SERVER_DIR/.env" ]] || return 0
    append_env_if_missing "PROJECT_DOMAIN" ""
    append_env_if_missing "SERVER_RELOAD" "False"
    append_env_if_missing "SERVER_SSL_CERTFILE" ""
    append_env_if_missing "SERVER_SSL_KEYFILE" ""
    append_env_if_missing "ADAPTERS" "[\"qq\",\"ws\"]"
    append_env_if_missing "QQ_EVENT_PATH" "$DEFAULT_QQ_EVENT_PATH"
    append_env_if_missing "QQ_BOT_APP_ID" ""
    append_env_if_missing "QQ_BOT_SECRET" ""
}

read_server_settings() {
    read_or SERVER_PORT "服务端端口 SERVER_PORT" "$DEFAULT_SERVER_PORT"
    read_or PROJECT_DOMAIN "公开域名 PROJECT_DOMAIN，可留空或带 https:// 与端口" ""
    read_or SERVER_SSL_CERTFILE "HTTPS 证书路径 SERVER_SSL_CERTFILE，可留空" ""
    read_or SERVER_SSL_KEYFILE "HTTPS 私钥路径 SERVER_SSL_KEYFILE，可留空" ""
    read_or ADAPTERS_RAW "启用适配器 ADAPTERS，逗号分隔" "$DEFAULT_ADAPTERS"
    ADAPTERS_LIST="$(make_adapter_list "$ADAPTERS_RAW")"
    read_or QQ_EVENT_PATH "QQ webhook 路径 QQ_EVENT_PATH" "$DEFAULT_QQ_EVENT_PATH"
    read_or QQ_BOT_APP_ID "QQ 机器人 AppID，可留空" ""
    read_or QQ_BOT_SECRET "QQ 机器人 Secret，可留空" ""
}

patch_plugin_ws_url() {
    local port="$1"
    local ws_base="ws://127.0.0.1:${port}/ws/bot"
    [[ -f "$API_PY" ]] || return 1
    python3 - "$API_PY" "$ws_base" <<'PY'
import re, sys
path, ws = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
text, n = re.subn(r'(base_url:\s*str\s*=\s*)["\']ws://[^"\']+["\']', rf'\1"{ws}"', text, count=1)
if n != 1: raise SystemExit(1)
open(path, "w", encoding="utf-8").write(text)
PY
    show_status "插件 WS → ${ws_base}" "success"
}

write_bot_pyproject() {
    cat > "$BOT_DIR/pyproject.toml" <<'EOF'
[project]
name = "xiuxian3-bot"
version = "0.1.0"
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
    show_status "NoneBot 配置" "success"
}

create_venv() {
    if [[ ! -d "$VENV_PATH" ]]; then
        python3 -m venv "$VENV_PATH" || return 1
    fi
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate" || return 1
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple >/dev/null 2>&1 || true
    pip install -U pip
    show_status "虚拟环境" "success"
}

install_python_deps() {
    source "$VENV_PATH/bin/activate"
    pip install -U -r "$SERVER_DIR/requirements.txt" || return 1
    pip install -U nb-cli \
        "nonebot2[fastapi,httpx,websockets,aiohttp]" \
        nonebot-adapter-onebot nonebot-adapter-qq \
        nonebot_plugin_apscheduler "websockets>=12.0" || return 1
    show_status "Python 依赖" "success"
}

install_management_scripts() {
    ensure_dir "$BIN_DIR"
    local mgr="$BIN_DIR/$PROJECT_NAME"
    local server_start="$BIN_DIR/${PROJECT_NAME}_server_start"
    local bot_start="$BIN_DIR/${PROJECT_NAME}_bot_start"

    cat > "$server_start" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
export TZ=Asia/Shanghai
source "$VENV_PATH/bin/activate"
cd "$SERVER_DIR" || exit 1
exec python main.py
EOF

    cat > "$bot_start" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
export TZ=Asia/Shanghai
source "$VENV_PATH/bin/activate"
cd "$BOT_DIR" || exit 1
exec nb run
EOF

    cat > "$mgr" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
ROOT="$ROOT"
PROJECT_NAME="$PROJECT_NAME"
DIR="$ROOT"
SERVER_START="$server_start"
BOT_START="$bot_start"
VENV_PATH="$VENV_PATH"

screen_name() { echo "\${PROJECT_NAME}_\$1"; }

case "\${1:-start}" in
    start-server)
        sn=\$(screen_name server)
        if screen -list | grep -qF "\$sn"; then echo "服务端已在运行"; else
            screen -U -dmS "\$sn" -L -Logfile "\$DIR/logs/server.log" "$TERMUX_PREFIX/bin/bash" "\$SERVER_START"
            echo "已启动服务端"
        fi ;;
    start-bot)
        sn=\$(screen_name bot)
        if screen -list | grep -qF "\$sn"; then echo "机器人已在运行"; else
            screen -U -dmS "\$sn" -L -Logfile "\$DIR/logs/bot.log" "$TERMUX_PREFIX/bin/bash" "\$BOT_START"
            echo "已启动机器人"
        fi ;;
    start)
        "\$0" start-server
        sleep 2
        "\$0" start-bot ;;
    stop-server) screen -X -S "\$(screen_name server)" quit 2>/dev/null ;;
    stop-bot) screen -X -S "\$(screen_name bot)" quit 2>/dev/null ;;
    stop) "\$0" stop-bot; "\$0" stop-server ;;
    status-server) screen -U -r "\$(screen_name server)" ;;
    status-bot) screen -U -r "\$(screen_name bot)" ;;
    update-deps)
        source "\$VENV_PATH/bin/activate"
        pip install -U -r "\$ROOT/server/requirements.txt"
        pip install -U nb-cli "nonebot2[fastapi,httpx,websockets,aiohttp]" nonebot-adapter-onebot nonebot-adapter-qq nonebot_plugin_apscheduler websockets
        ;;
    *)
        echo "用法: \$PROJECT_NAME {start|start-server|start-bot|stop|status-server|status-bot|update-deps}"
        ;;
esac
EOF
    chmod +x "$mgr" "$server_start" "$bot_start"
    show_status "命令 $mgr" "success"
}

final_message() {
    local sp nb event_path project_domain ssl_cert ssl_key scheme host callback
    sp=$(grep -E '^SERVER_PORT=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2)
    nb=$(grep -E '^PORT *= *' "$BOT_DIR/.env.dev" 2>/dev/null | sed -E 's/.*= *//')
    event_path=$(grep -E '^QQ_EVENT_PATH=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2)
    project_domain=$(grep -E '^PROJECT_DOMAIN=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2-)
    ssl_cert=$(grep -E '^SERVER_SSL_CERTFILE=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2-)
    ssl_key=$(grep -E '^SERVER_SSL_KEYFILE=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2-)
    [[ -z "$sp" ]] && sp="$DEFAULT_SERVER_PORT"
    [[ -z "$nb" ]] && nb="$DEFAULT_NB_PORT"
    [[ -z "$event_path" ]] && event_path="$DEFAULT_QQ_EVENT_PATH"
    scheme="http"
    [[ -n "$ssl_cert" && -n "$ssl_key" ]] && scheme="https"
    host="${project_domain:-127.0.0.1}"
    if [[ "$host" == http://* || "$host" == https://* ]]; then
        callback="${host%/}${event_path}"
    elif [[ "$host" == *:* ]]; then
        callback="${scheme}://${host}${event_path}"
    else
        callback="${scheme}://${host}:${sp}${event_path}"
    fi
    ui_print green "========================================"
    ui_print green "完成: $ACTION"
    ui_print white "目录: $ROOT"
    ui_print white "QQ webhook: ${callback}"
    ui_print white "服务端 ws://127.0.0.1:${sp}/ws/bot/{id}"
    ui_print white "OneBot ws://127.0.0.1:${nb}/onebot/v11/ws"
    ui_print cyan "QQ webhook 只需 $PROJECT_NAME start-server；OneBot 桥接再启动 $PROJECT_NAME start-bot"
    ui_print green "========================================"
}

main() {
    detect_termux
    parse_args "$@"
    resolve_paths
    ui_print cyan "$ACTION → $ROOT"

    if [[ "$ACTION" == "reinstall" ]]; then
        read_or c "删除 $ROOT 输入 YES" "NO"
        [[ "$c" == "YES" ]] || exit 0
        rm -rf "$ROOT"
        ACTION="install"
    fi

    if [[ "$ACTION" == "update-deps" ]]; then
        [[ -d "$VENV_PATH" ]] || exit 127
        create_venv && install_python_deps && final_message
        exit 0
    fi

    if [[ "$ACTION" == "install" && -f "$SERVER_DIR/main.py" ]]; then
        ui_print red "已存在，请 update 或重装"
        exit 127
    fi

    install_termux_packages || exit 127
    ensure_dir "$ROOT"
    clone_or_update_repo || exit 127

    if [[ "$ACTION" == "update" && -f "$SERVER_DIR/.env" ]]; then
        cp "$SERVER_DIR/.env" "$ROOT/.env.keep"
    fi
    sync_tree || exit 127
    [[ -f "$ROOT/.env.keep" ]] && mv "$ROOT/.env.keep" "$SERVER_DIR/.env"

    if [[ "$ACTION" == "install" ]]; then
        read_server_settings
        read_or SUPERUSERS "主人QQ" "123456"
        read_or NICKNAME "昵称" "修仙助手"
        read_or NB_PORT "NoneBot端口" "$DEFAULT_NB_PORT"
        write_bot_env "$SUPERUSERS" "$NICKNAME" "$NB_PORT"
        write_bot_pyproject
        install_management_scripts
    else
        SERVER_PORT=$(grep -E '^SERVER_PORT=' "$SERVER_DIR/.env" 2>/dev/null | cut -d= -f2)
        [[ -z "$SERVER_PORT" ]] && SERVER_PORT="$DEFAULT_SERVER_PORT"
        [[ -f "$BOT_DIR/pyproject.toml" ]] || write_bot_pyproject
    fi

    write_server_env "$SERVER_PORT"
    ensure_server_env_defaults
    patch_plugin_ws_url "$SERVER_PORT" || exit 127
    create_venv || exit 127
    install_python_deps || exit 127
    final_message
}

main "$@"
