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
PORT="${3:-8745}"

if [ ! -f "$SO_PATH" ]; then
  echo "SO 不存在: $SO_PATH" >&2
  exit 1
fi

mkdir -p "$WORKSPACE_DIR"
SO_NAME="$(basename "$SO_PATH")"
if [ "$SO_PATH" != "$WORKSPACE_DIR/$SO_NAME" ]; then
  cp -f "$SO_PATH" "$WORKSPACE_DIR/$SO_NAME"
fi

export WORKSPACE_DIR IDA_PORT="$PORT" IDA_INPUT_PATH="/work/$SO_NAME"
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
  if docker compose -f "$COMPOSE_FILE" --profile ida-only ps --all --services 2>/dev/null | grep . >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" --profile ida-only down --remove-orphans
  fi
}

trap cleanup EXIT INT TERM

echo "[run-ida-sidecar] SO=$WORKSPACE_DIR/$SO_NAME"
echo "[run-ida-sidecar] MCP=http://127.0.0.1:${PORT}/mcp"
if [ -n "${HTTP_PROXY:-}" ]; then
  echo "[run-ida-sidecar] HTTP_PROXY=$HTTP_PROXY"
fi
echo "[run-ida-sidecar] 停止时将自动执行: docker compose down --remove-orphans"

docker compose -f "$COMPOSE_FILE" --profile ida-only up ida-sidecar
