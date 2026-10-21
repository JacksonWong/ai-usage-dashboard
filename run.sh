#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"
UV_BIN="$(command -v uv || true)"

if [ -z "$UV_BIN" ]; then
  echo "需要 uv（https://docs.astral.sh/uv/）来管理依赖：pip install uv" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> 创建虚拟环境 .venv"
  "$UV_BIN" venv .venv
fi

echo "==> 安装依赖"
"$UV_BIN" pip install --python .venv/bin/python --quiet \
  fastapi "uvicorn[standard]" httpx cryptography pytest pytest-asyncio

echo "==> 启动 http://${HOST}:${PORT}"
exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
