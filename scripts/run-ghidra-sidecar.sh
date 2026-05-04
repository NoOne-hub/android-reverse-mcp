#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法: $0 /absolute/path/to/lib.so [workspace_dir] [port]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"

SO_PATH="$(realpath "$1")"
WORKSPACE_DIR="${2:-$(dirname "$SO_PATH")}"
PORT="${3:-8765}"

if [ ! -f "$SO_PATH" ]; then
  echo "SO 不存在: $SO_PATH" >&2
  exit 1
fi

require_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "[run-ghidra-sidecar] 缺少文件: $path" >&2
    return 1
  fi
}

require_file "$REPO_ROOT/third_party/ghidra_12.0.4_PUBLIC_20260303.zip"
require_file "$REPO_ROOT/third_party/ghidra-headless-mcp-b9c491a6383dbc68c581e7fed16341ac47e7faba.zip"

mkdir -p "$WORKSPACE_DIR"
SO_NAME="$(basename "$SO_PATH")"
if [ "$SO_PATH" != "$WORKSPACE_DIR/$SO_NAME" ]; then
  cp -f "$SO_PATH" "$WORKSPACE_DIR/$SO_NAME"
fi

export WORKSPACE_DIR GHIDRA_PORT="$PORT"
if [ -n "${HTTP_PROXY:-}" ]; then
  export HTTP_PROXY
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
  export HTTPS_PROXY
fi
if [ -n "${ALL_PROXY:-}" ]; then
  export ALL_PROXY
fi

cleanup() {
  if docker compose -f "$COMPOSE_FILE" --profile ghidra-only ps --all --services 2>/dev/null | grep . >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" --profile ghidra-only down --remove-orphans
  fi
}

trap cleanup EXIT INT TERM

echo "[run-ghidra-sidecar] SO=$WORKSPACE_DIR/$SO_NAME"
echo "[run-ghidra-sidecar] MCP=tcp://127.0.0.1:${PORT}"
echo "[run-ghidra-sidecar] 用 MCP 客户端调用 program.open 时传: /workspace/$SO_NAME"
if [ -n "${HTTP_PROXY:-}" ]; then
  echo "[run-ghidra-sidecar] HTTP_PROXY=$HTTP_PROXY"
fi
echo "[run-ghidra-sidecar] 停止时将自动执行: docker compose down --remove-orphans"

docker compose -f "$COMPOSE_FILE" --profile ghidra-only up --build ghidra-sidecar
