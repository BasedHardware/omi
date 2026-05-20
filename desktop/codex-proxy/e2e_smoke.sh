#!/usr/bin/env bash
# End-to-end smoke tests for omi-codex-proxy (requires valid ~/.codex/auth.json).
set -euo pipefail

PORT="${OMI_CODEX_PROXY_PORT:-10531}"
BASE="http://127.0.0.1:${PORT}"
PROXY_BIN="$(cd "$(dirname "$0")" && pwd)/target/release/omi-codex-proxy"

if ! curl -fsS "${BASE}/health" >/dev/null 2>&1; then
  if [[ ! -x "$PROXY_BIN" ]]; then
    echo "Building proxy..."
    (cd "$(dirname "$0")" && cargo build --release)
  fi
  echo "Starting proxy on ${PORT}..."
  "$PROXY_BIN" &
  PROXY_PID=$!
  trap 'kill "$PROXY_PID" 2>/dev/null || true' EXIT
  for _ in $(seq 1 30); do
    curl -fsS "${BASE}/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
fi

python3 <<'PY'
import json, urllib.request, textwrap, sys

BASE = f"http://127.0.0.1:{__import__('os').environ.get('OMI_CODEX_PROXY_PORT', '10531')}/v1/chat/completions"

def post(messages, label):
    payload = {"model": "gpt-5.4", "messages": messages, "temperature": 0.2, "stream": False}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
        text = data["choices"][0]["message"]["content"].strip()
        assert text, f"empty response for {label}"
        print(f"PASS {label}: {text[:80]!r}")
        return text
    except Exception as e:
        body = e.read().decode()[:400] if hasattr(e, "read") else str(e)
        print(f"FAIL {label}: {body}", file=sys.stderr)
        raise

post([{"role": "system", "content": "You are Omi."}, {"role": "user", "content": "Reply with exactly: alpha"}], "single-turn")
post([
    {"role": "system", "content": "You are Omi."},
    {"role": "user", "content": "hey"},
    {"role": "assistant", "content": "Hey!"},
    {"role": "user", "content": "What is 2+2? Reply with just the number."},
], "multi-turn")
post([
    {"role": "system", "content": "You are Omi.\n" + ("Context line.\n" * 20)},
    {"role": "user", "content": "Reply with exactly: ready"},
], "large-system")
post([{"role": "user", "content": "Reply with exactly: default"}], "default-instructions")
post([
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": [{"type": "text", "text": "Reply with exactly: array-ok"}]},
], "hybrid-llm-array-content")
print("ALL PROXY E2E CHECKS PASSED")
PY

echo "e2e_smoke: OK"
