#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
cd "$(dirname "$0")/../.."

DESKTOP_BACKEND_URL="${OMI_DESKTOP_API_URL:-http://127.0.0.1:10201}"
STATE_ROOT="${OMI_LOCAL_STATE_ROOT:-.local/dev-harness/default}"
BACKEND_LOG="${STATE_ROOT}/logs/backend.log"
OMI_CTL="./desktop/macos/scripts/omi-ctl"

failures=0

echo "Omi local dev harness verification"

if [ -x "$OMI_CTL" ]; then
  deadline=$((SECONDS + 30))
  signed_in=false
  while [ "$SECONDS" -lt "$deadline" ]; do
    if state_json="$("$OMI_CTL" state 2>/dev/null)"; then
      if echo "$state_json" | grep -q '"isSignedIn"[[:space:]]*:[[:space:]]*true'; then
        signed_in=true
        echo "omi-ctl state: isSignedIn=true"
        break
      fi
    fi
    sleep 2
  done
  if [ "$signed_in" != true ]; then
    echo "omi-ctl state: isSignedIn not true within 30s (is Omi Dev running?)" >&2
    failures=$((failures + 1))
  fi
else
  echo "warning: $OMI_CTL not found; skipping omi-ctl state check"
fi

chat_status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${DESKTOP_BACKEND_URL}/v2/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' || true)"
if [ "$chat_status" = "404" ]; then
  echo "chat smoke: POST /v2/chat/completions returned 404" >&2
  failures=$((failures + 1))
else
  echo "chat smoke: POST /v2/chat/completions returned HTTP ${chat_status:-unknown} (non-404)"
fi

if [ -f "$BACKEND_LOG" ]; then
  aud_count="$(grep -c 'incorrect "aud"' "$BACKEND_LOG" 2>/dev/null || true)"
  if [ "${aud_count:-0}" -gt 0 ]; then
    echo "backend log: found ${aud_count} incorrect \"aud\" errors in $BACKEND_LOG" >&2
    failures=$((failures + 1))
  else
    echo "backend log: no incorrect \"aud\" errors"
  fi
else
  echo "warning: backend log not found at $BACKEND_LOG"
fi

if [ "$failures" -gt 0 ]; then
  echo "dev-verify failed ($failures check(s))" >&2
  exit 1
fi

echo "dev-verify passed"
