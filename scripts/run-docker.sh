#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法: $0 /absolute/path/to/app.apk [workspace_dir] [port]" >&2
  exit 1
fi

APK_PATH="$(realpath "$1")"
WORKSPACE_DIR="${2:-$(pwd)/.workspaces/$(basename "${APK_PATH%.*}")}"
PORT="${3:-8651}"
IMAGE="${IMAGE:-android-reverse-mcp:latest}"

if [ ! -f "$APK_PATH" ]; then
  echo "APK 不存在: $APK_PATH" >&2
  exit 1
fi

mkdir -p "$WORKSPACE_DIR"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[run-docker] 本地镜像不存在，开始构建: $IMAGE"
  docker build -t "$IMAGE" .
fi

echo "[run-docker] APK=$APK_PATH"
echo "[run-docker] WORKSPACE=$WORKSPACE_DIR"
echo "[run-docker] MCP=http://127.0.0.1:${PORT}/mcp"

exec docker run --rm -it \
  -p "${PORT}:8651" \
  -v "${WORKSPACE_DIR}:/workspace" \
  -v "${APK_PATH}:/input/app.apk:ro" \
  -e APK=/input/app.apk \
  -e DECODE_ON_START=1 \
  "$IMAGE"
