#!/usr/bin/env bash
set -euo pipefail

HOST_VALUE="${HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-8765}"

if [ -z "${GHIDRA_INSTALL_DIR:-}" ] && [ -d /opt/ghidra ]; then
  GHIDRA_INSTALL_DIR="$(find /opt/ghidra -maxdepth 1 -mindepth 1 -type d -name 'ghidra_*_PUBLIC' | sort | head -n 1 || true)"
  export GHIDRA_INSTALL_DIR
fi

ARGS=(--transport tcp --host "$HOST_VALUE" --port "$PORT_VALUE")
if [ "${GHIDRA_HEADLESS_MCP_FAKE_BACKEND:-0}" = "1" ]; then
  ARGS+=(--fake-backend)
elif [ -n "${GHIDRA_INSTALL_DIR:-}" ]; then
  ARGS+=(--ghidra-install-dir "$GHIDRA_INSTALL_DIR")
else
  echo "[ghidra-sidecar] GHIDRA_INSTALL_DIR 未配置，且未启用 fake backend" >&2
  exit 1
fi

exec ghidra-headless-mcp "${ARGS[@]}"
