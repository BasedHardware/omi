#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
exec ./venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080 --env-file .env
