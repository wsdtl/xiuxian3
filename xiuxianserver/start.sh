#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"
APP_ENTRY="${APP_ENTRY:-main.py}"
HASH_FILE="$VENV_DIR/.requirements.sha256"

log() {
    printf '[xiuxian-start] %s\n' "$*"
}

fail() {
    printf '[xiuxian-start][error] %s\n' "$*" >&2
    exit 1
}

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    fail "未找到 $REQUIREMENTS_FILE，请确认启动脚本位于 xiuxianserver 目录。"
fi

if [ ! -f "$APP_ENTRY" ]; then
    fail "未找到 $APP_ENTRY，请确认服务端入口文件存在。"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "创建 Python 虚拟环境：$VENV_DIR"
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        fail "创建虚拟环境失败。Ubuntu 可安装 python3-venv；Docker 请换用带 venv 的 Python 运行环境。"
    fi
fi

REQ_HASH="$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}')"
OLD_HASH=""
if [ -f "$HASH_FILE" ]; then
    OLD_HASH="$(cat "$HASH_FILE")"
fi

if [ "$REQ_HASH" != "$OLD_HASH" ]; then
    log "安装或更新 Python 依赖"
    "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel
    "$VENV_DIR/bin/python" -m pip install --no-cache-dir -r "$REQUIREMENTS_FILE"
    printf '%s\n' "$REQ_HASH" > "$HASH_FILE"
else
    log "依赖未变化，跳过安装"
fi

log "启动修仙服务端"
exec "$VENV_DIR/bin/python" "$APP_ENTRY" "$@"
