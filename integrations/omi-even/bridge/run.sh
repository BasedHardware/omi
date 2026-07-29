#!/usr/bin/env bash
# Start the omi <-> Even Realities bridge and expose it for the glasses.
#
# Brings up three things:
#   1. the bridge (FastAPI) on $PORT
#   2. a Cloudflare tunnel, so the Even app can reach it over HTTPS
#   3. a printed summary with the exact values to paste into "Add Agent"
#
# The token is persisted to .env on first run so the URL you register in the
# Even app keeps working across restarts. The *tunnel URL* does not survive a
# restart unless you use a named tunnel -- see the note printed at the end.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8788}"
ENV_FILE=".env"

if [ ! -d .venv ]; then
  echo "No .venv found. Creating one..."
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/python -m pip install -q fastapi "uvicorn[standard]" httpx websockets pytest
fi

# A stable shared secret: regenerating it on every run would silently break the
# agent already registered on the phone.
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi
if [ -z "${OMI_EVEN_TOKEN:-}" ]; then
  OMI_EVEN_TOKEN="omi-even-$(python3 -c 'import secrets;print(secrets.token_hex(12))')"
  printf 'OMI_EVEN_TOKEN=%s\n' "$OMI_EVEN_TOKEN" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Generated a new bridge token and saved it to $ENV_FILE"
fi
export OMI_EVEN_TOKEN

cleanup() {
  [ -n "${BRIDGE_PID:-}" ] && kill "$BRIDGE_PID" 2>/dev/null || true
  [ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting bridge on :$PORT ..."
./.venv/bin/uvicorn server:app --host 0.0.0.0 --port "$PORT" > /tmp/omi-even-server.log 2>&1 &
BRIDGE_PID=$!

# Wait for readiness rather than sleeping a fixed amount -- the first request
# also performs the Firebase refresh, which can take a couple of seconds.
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/health"; then break; fi
  sleep 1
done

if ! curl -sf -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/health"; then
  echo "Bridge failed to start. Last log lines:" >&2
  tail -20 /tmp/omi-even-server.log >&2
  exit 1
fi

TUNNEL_URL=""
if [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; then
  if ! command -v cloudflared > /dev/null; then
    echo "cloudflared not found (brew install cloudflared). Continuing without a tunnel." >&2
  else
    echo "Starting tunnel ..."
    cloudflared tunnel --url "http://localhost:$PORT" > /tmp/omi-even-tunnel.log 2>&1 &
    TUNNEL_PID=$!
    for _ in $(seq 1 40); do
      TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/omi-even-tunnel.log | head -1 || true)"
      [ -n "$TUNNEL_URL" ] && break
      sleep 1
    done
  fi
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || echo '')"

cat <<EOF

  omi bridge is running.

  Register in the Even Realities app -> Add Agent:
     Name:   omi
     URL:    ${TUNNEL_URL:-<no tunnel; use http://${LAN_IP:-127.0.0.1}:$PORT>}
     Token:  $OMI_EVEN_TOKEN

  For the omi Hub app on the glasses:
     ws://${LAN_IP:-127.0.0.1}:$PORT/app

  Health:  curl -s http://127.0.0.1:$PORT/health
  Logs:    /tmp/omi-even-server.log
  Captured Add Agent requests: $(pwd)/add-agent-capture.log

  Note: a quick tunnel gets a NEW URL every restart, so you would have to
  re-register in the Even app each time. For a URL that survives restarts,
  set up a named tunnel: cloudflared tunnel create omi-even

  Ctrl-C to stop.

EOF

wait $BRIDGE_PID
