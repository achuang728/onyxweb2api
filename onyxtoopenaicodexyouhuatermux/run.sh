#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8896}"

exec python -m uvicorn main:app --host "$HOST" --port "$PORT" --loop asyncio
