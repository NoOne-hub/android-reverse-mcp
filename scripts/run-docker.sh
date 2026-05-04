#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法: $0 /absolute/path/to/app.apk [workspace_dir] [port] [ghidra|ida]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"

APK_PATH="$(realpath "$1")"
WORKSPACE_DIR="${2:-$REPO_ROOT/.workspaces/$(basename "${APK_PATH%.*}")}"
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
if [ -n "${HTTP_PROXY:-}" ]; then
  export HTTP_PROXY
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  export HTTPS_PROXY
fi
if [ -n "${ALL_PROXY:-}" ]; then
  export ALL_PROXY
fi
if [ -n "${IDA_PORT:-}" ]; then
  export IDA_PORT
fi

require_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "[run-docker] 缺少文件: $path" >&2
    return 1
  fi
}

require_local_artifacts() {
  require_file "$REPO_ROOT/java-backend/target/headless-jadx-backend-0.1.0.jar"
  require_file "$REPO_ROOT/java-backend/lib/jadx-1.5.5-all.jar"
  if [ "$NATIVE_BACKEND" = "ghidra" ]; then
    require_file "$REPO_ROOT/third_party/ghidra_12.0.4_PUBLIC_20260303.zip"
    require_file "$REPO_ROOT/third_party/ghidra-headless-mcp-b9c491a6383dbc68c581e7fed16341ac47e7faba.zip"
  fi
}

mkdir -p "$WORKSPACE_DIR"
require_local_artifacts

cleanup() {
  if docker compose -f "$COMPOSE_FILE" --profile "$PROFILE" ps --all --services 2>/dev/null | grep . >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" --profile "$PROFILE" down --remove-orphans
  fi
}

trap cleanup EXIT INT TERM

echo "[run-docker] APK=$APK_PATH"
echo "[run-docker] WORKSPACE=$WORKSPACE_DIR"
echo "[run-docker] MCP=http://127.0.0.1:${PORT}/mcp"
echo "[run-docker] NATIVE_BACKEND=$NATIVE_BACKEND"
echo "[run-docker] NATIVE_BACKEND_URL=$NATIVE_BACKEND_URL"
if [ -n "${HTTP_PROXY:-}" ]; then
  echo "[run-docker] HTTP_PROXY=$HTTP_PROXY"
fi
echo "[run-docker] 停止时将自动执行: docker compose down --remove-orphans"

if [ "$NATIVE_BACKEND" = "ida" ]; then
  docker compose -f "$COMPOSE_FILE" --profile "$PROFILE" up
else
  docker compose -f "$COMPOSE_FILE" --profile "$PROFILE" up --build
fi
