#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=_source_local_dev_env.sh
source "$SCRIPT_DIR/_source_local_dev_env.sh"
cd "$REPO_ROOT"

DESKTOP_BACKEND_URL="${OMI_DESKTOP_API_URL:-http://127.0.0.1:10201}"
STATE_ROOT="${OMI_LOCAL_STATE_ROOT:-.local/dev-harness/default}"
BACKEND_LOG="${STATE_ROOT}/logs/backend.log"
OMI_CTL="./desktop/macos/scripts/omi-ctl"
APP_CONFIG="./desktop/macos/scripts/app-config.sh"

# Resolve the named-bundle automation target. Prefer an explicit
# OMI_AUTOMATION_PORT, then AUTOMATION_PORT (run.sh / worktree isolation), then
# the worktree-derived default from scripts/dev-instance.sh. Never silently fall
# back to 47777 when a linked worktree or named bundle already bound another port.
resolve_verify_automation_env() {
  local app_name=""
  if [[ -z "${OMI_AUTOMATION_PORT:-}" && -z "${AUTOMATION_PORT:-}" && -f "$REPO_ROOT/scripts/dev-instance.sh" ]]; then
    # shellcheck source=../../scripts/dev-instance.sh
    source "$REPO_ROOT/scripts/dev-instance.sh"
  fi
  export OMI_AUTOMATION_PORT="${OMI_AUTOMATION_PORT:-${AUTOMATION_PORT:-47777}}"
  app_name="${OMI_APP_NAME:-${DESKTOP_APP_NAME:-}}"
  if [[ -n "$app_name" ]]; then
    export OMI_APP_NAME="$app_name"
  fi
  printf '%s\n' "$OMI_AUTOMATION_PORT"
}

expected_bundle_id_for_app() {
  local app_name="${1:-}"
  if [[ -z "$app_name" ]]; then
    return 1
  fi
  # shellcheck source=../../desktop/macos/scripts/app-config.sh
  source "$APP_CONFIG"
  derive_omi_app_config "$app_name" || return 1
  printf '%s\n' "$BUNDLE_ID"
}

# Pure seam: validate an unauthenticated /health identity payload against the
# expected named-bundle id. Used by live verify and --self-test.
assert_health_identity() {
  local expected_bundle_id="$1"
  local health_json="$2"
  python3 - "$expected_bundle_id" "$health_json" <<'PY'
import json
import sys

expected, raw = sys.argv[1:3]
payload = json.loads(raw)
if not payload.get("ok"):
    raise SystemExit(f"bridge unhealthy: {payload}")
actual = payload.get("bundleIdentifier")
if actual != expected:
    raise SystemExit(f"wrong bundle on automation port: expected {expected}, got {actual}")
bridge_port = payload.get("bridgePort")
print(f"health identity ok: bundleIdentifier={actual} bridgePort={bridge_port}")
PY
}

run_self_test() {
  local resolved expected
  resolved="$(
    OMI_AUTOMATION_PORT=47999 AUTOMATION_PORT=47888 \
      resolve_verify_automation_env
  )"
  [[ "$resolved" == "47999" ]] || {
    echo "self-test: explicit OMI_AUTOMATION_PORT must win (got $resolved)" >&2
    exit 1
  }

  resolved="$(
    env -u OMI_AUTOMATION_PORT AUTOMATION_PORT=47950 \
      bash -c "$(declare -f resolve_verify_automation_env); resolve_verify_automation_env"
  )"
  [[ "$resolved" == "47950" ]] || {
    echo "self-test: AUTOMATION_PORT must be honored when OMI_AUTOMATION_PORT unset (got $resolved)" >&2
    exit 1
  }

  expected="$(expected_bundle_id_for_app "omi-qa")"
  [[ "$expected" == "com.omi.omi-qa" ]] || {
    echo "self-test: expected com.omi.omi-qa, got $expected" >&2
    exit 1
  }

  assert_health_identity "$expected" \
    '{"ok":true,"bundleIdentifier":"com.omi.omi-qa","bridgePort":47950}' >/dev/null
  if assert_health_identity "$expected" \
    '{"ok":true,"bundleIdentifier":"com.omi.desktop-dev","bridgePort":47777}' >/dev/null 2>&1; then
    echo "self-test: mismatched bundleIdentifier should fail" >&2
    exit 1
  fi

  echo "verify-desktop-local-launch self-test passed"
  exit 0
}

if [[ "${1:-}" == "--self-test" ]]; then
  run_self_test
fi

resolve_verify_automation_env >/dev/null
echo "Omi local dev harness verification (automation port ${OMI_AUTOMATION_PORT})"

failures=0

if [ -x "$OMI_CTL" ]; then
  deadline=$((SECONDS + 30))
  signed_in=false
  while [ "$SECONDS" -lt "$deadline" ]; do
    if state_json="$(OMI_AUTOMATION_PORT="$OMI_AUTOMATION_PORT" "$OMI_CTL" state 2>/dev/null)"; then
      if echo "$state_json" | grep -q '"isSignedIn"[[:space:]]*:[[:space:]]*true'; then
        signed_in=true
        echo "omi-ctl state: isSignedIn=true (port ${OMI_AUTOMATION_PORT})"
        break
      fi
    fi
    sleep 2
  done
  if [ "$signed_in" != true ]; then
    echo "omi-ctl state: isSignedIn not true within 30s on port ${OMI_AUTOMATION_PORT} (is the named bundle running?)" >&2
    failures=$((failures + 1))
  fi

  if [[ -n "${OMI_APP_NAME:-}" ]]; then
    expected_id="$(expected_bundle_id_for_app "$OMI_APP_NAME" || true)"
    if [[ -n "$expected_id" ]]; then
      if health_json="$(OMI_AUTOMATION_PORT="$OMI_AUTOMATION_PORT" "$OMI_CTL" health 2>/dev/null)"; then
        if assert_health_identity "$expected_id" "$health_json"; then
          :
        else
          failures=$((failures + 1))
        fi
      else
        echo "omi-ctl health: unavailable on port ${OMI_AUTOMATION_PORT} for ${OMI_APP_NAME}" >&2
        failures=$((failures + 1))
      fi
    fi
  fi
else
  echo "warning: $OMI_CTL not found; skipping omi-ctl state check"
fi

if python3 - "$REPO_ROOT" "$DESKTOP_BACKEND_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

repo_root = Path(sys.argv[1])
desktop_backend_url = sys.argv[2]
sys.path.insert(0, str(repo_root / "scripts" / "dev-harness"))
from dev_harness import config

cfg = config.load_config(repo_root)

def post_json(url, payload, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read() or b"{}")

_, signup = post_json(
    f"http://{cfg.auth_host}/identitytoolkit.googleapis.com/v1/accounts:signUp?key={config.LOCAL_FIREBASE_API_KEY}",
    {
        "email": f"omi-local-smoke-{uuid.uuid4()}@example.invalid",
        "password": uuid.uuid4().hex,
        "returnSecureToken": True,
    },
)
token = signup.get("idToken")
if not token:
    raise SystemExit("auth emulator did not return an idToken")
status, _ = post_json(
    f"{desktop_backend_url}/v2/chat/completions",
    {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    },
    {"Authorization": f"Bearer {token}"},
)
if not 200 <= status < 300:
    raise SystemExit(f"chat completion returned HTTP {status}")
print(f"chat smoke: authenticated POST /v2/chat/completions returned HTTP {status}")
PY
then
  :
else
  echo "chat smoke: authenticated completion failed" >&2
  failures=$((failures + 1))
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
