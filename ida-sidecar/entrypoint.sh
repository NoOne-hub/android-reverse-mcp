#!/usr/bin/env bash
set -euo pipefail

IDA_MCP_HOST="${IDA_MCP_HOST:-0.0.0.0}"
IDA_MCP_PORT="${IDA_MCP_PORT:-8745}"
IDADIR="${IDADIR:-/opt/ida-pro}"
IDA_USER_DIR="${IDA_USER_DIR:-/root/.idapro}"
EXTRA_ARGS=()

if [ ! -d "$IDADIR" ]; then
  echo "[ida-sidecar] IDA directory not found: $IDADIR" >&2
  exit 1
fi

mkdir -p "$IDA_USER_DIR"
export IDADIR
export IDAUSR="$IDA_USER_DIR"
export HOME="$(dirname "$IDA_USER_DIR")"
export LD_LIBRARY_PATH="$IDADIR:${LD_LIBRARY_PATH:-}"

if [ "${IDA_MCP_ISOLATED_CONTEXTS:-0}" = "1" ] || [ "${IDA_MCP_ISOLATED_CONTEXTS:-false}" = "true" ]; then
  EXTRA_ARGS+=(--isolated-contexts)
fi

if [ "${IDA_MCP_UNSAFE:-0}" = "1" ] || [ "${IDA_MCP_UNSAFE:-false}" = "true" ]; then
  EXTRA_ARGS+=(--unsafe)
fi

if [ -n "${IDA_MCP_PROFILE:-}" ]; then
  EXTRA_ARGS+=(--profile "$IDA_MCP_PROFILE")
fi

echo "[ida-sidecar] IDADIR=$IDADIR"
echo "[ida-sidecar] IDAUSR=$IDAUSR"
exec /opt/ida-pro-mcp-venv/bin/idalib-mcp --host "$IDA_MCP_HOST" --port "$IDA_MCP_PORT" "${EXTRA_ARGS[@]}"
