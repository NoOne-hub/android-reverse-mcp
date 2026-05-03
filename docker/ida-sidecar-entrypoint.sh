#!/usr/bin/env bash
set -euo pipefail

HOST_VALUE="${HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-8745}"
INPUT_PATH_VALUE="${IDA_INPUT_PATH:-}"

if [ -n "$INPUT_PATH_VALUE" ]; then
  exec idalib-mcp --host "$HOST_VALUE" --port "$PORT_VALUE" "$INPUT_PATH_VALUE"
fi

exec idalib-mcp --host "$HOST_VALUE" --port "$PORT_VALUE"
