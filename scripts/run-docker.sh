#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法: $0 /absolute/path/to/app.apk [workspace_dir] [port] [ghidra|ida]" >&2
  exit 1
fi

APK_PATH="$(realpath "$1")"
WORKSPACE_DIR="${2:-$(pwd)/.workspaces/$(basename "${APK_PATH%.*}")}"
PORT="${3:-8651}"
NATIVE_BACKEND="${NATIVE_BACKEND:-${4:-ghidra}}"

if [ ! -f "$APK_PATH" ]; then
  echo "APK 不存在: $APK_PATH" >&2
  exit 1
fi

case "$NATIVE_BACKEND" in
  ghidra)
    PROFILE="full-ghidra"
    NATIVE_BACKEND_PORT="${NATIVE_BACKEND_PORT:-8765}"
    ;;
  ida)
    PROFILE="full-ida"
    NATIVE_BACKEND_PORT="${NATIVE_BACKEND_PORT:-8745}"
    IDA_PORT="${IDA_PORT:-8745}"
    ;;
  *)
    echo "不支持的 native backend: $NATIVE_BACKEND" >&2
    exit 1
    ;;
esac

case "$NATIVE_BACKEND" in
  ghidra)
    NATIVE_BACKEND_URL="${NATIVE_BACKEND_URL:-tcp://ghidra-sidecar:${NATIVE_BACKEND_PORT}}"
    ;;
  ida)
    NATIVE_BACKEND_URL="${NATIVE_BACKEND_URL:-http://ida-sidecar:${NATIVE_BACKEND_PORT}/mcp}"
    ;;
esac
DECODE_ON_START="${DECODE_ON_START:-1}"
export APK_PATH WORKSPACE_DIR PORT NATIVE_BACKEND NATIVE_BACKEND_PORT NATIVE_BACKEND_URL DECODE_ON_START
if [ -n "${IDA_PORT:-}" ]; then
  export IDA_PORT
fi

mkdir -p "$WORKSPACE_DIR"

echo "[run-docker] APK=$APK_PATH"
echo "[run-docker] WORKSPACE=$WORKSPACE_DIR"
echo "[run-docker] MCP=http://127.0.0.1:${PORT}/mcp"
echo "[run-docker] NATIVE_BACKEND=$NATIVE_BACKEND"
echo "[run-docker] NATIVE_BACKEND_URL=$NATIVE_BACKEND_URL"

exec docker compose --profile "$PROFILE" up --build
