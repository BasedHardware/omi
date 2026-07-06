#!/usr/bin/env bash
# Bless a macOS desktop beta release by rebuilding the tag and running T2 core E2E.
#
# Usage:
#   ./scripts/bless-release.sh v11.0.0+11000-macos
#   ./scripts/bless-release.sh --keep-stack v11.0.0+11000-macos
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
KEYVALUE_PY="$SCRIPT_DIR/release-keyvalue.py"

KEEP_STACK=0
RELEASE_TAG=""

usage() {
  cat <<'USAGE'
Bless a macOS desktop beta release (rebuild tag + T2 core E2E + write blessed metadata).

Usage:
  bless-release.sh [--keep-stack] <vX.Y.Z+BUILD-macos>

Options:
  --keep-stack   Leave dev-harness stack running on exit (default: make dev-down)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-stack)
      KEEP_STACK=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$RELEASE_TAG" ]]; then
        echo "unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      RELEASE_TAG="$1"
      shift
      ;;
  esac
done

if [[ -z "$RELEASE_TAG" ]]; then
  usage >&2
  exit 2
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "bless-release.sh requires macOS" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "bless-release.sh requires gh CLI" >&2
  exit 1
fi

VERSION="${RELEASE_TAG#v}"
VERSION="${VERSION%-macos}"
BUNDLE="omi-bless-${VERSION}"
WORKTREE="$REPO_ROOT/.bless-worktrees/$RELEASE_TAG"
LAUNCH_LOG=""
DESKTOP_LAUNCH_PID=""
BLESS_SUCCESS=0
BRIDGE_WAIT_SECS=900

gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json tagName,isDraft,isPrerelease,body \
  > /tmp/bless-release.json

python3 "$KEYVALUE_PY" preflight-release /tmp/bless-release.json "$RELEASE_TAG"

SHA=$(git -C "$REPO_ROOT" rev-list -n1 "$RELEASE_TAG")

rm -rf "$WORKTREE"
git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" "$RELEASE_TAG"

LAUNCH_LOG="$WORKTREE/.bless-desktop-launch.log"

resolve_automation_port() {
  (
    cd "$WORKTREE"
    # shellcheck source=../../scripts/dev-instance.sh
    source "$WORKTREE/scripts/dev-instance.sh"
    printf '%s\n' "$AUTOMATION_PORT"
  )
}

AUTOMATION_PORT="$(resolve_automation_port)"

derive_bundle_id() {
  local app_name="$1"
  # shellcheck source=app-config.sh
  source "$REPO_ROOT/desktop/macos/scripts/app-config.sh"
  derive_omi_app_config "$app_name"
  printf '%s\n' "$BUNDLE_ID"
}

kill_process_tree() {
  local pid="$1"
  local children child
  [[ -z "$pid" ]] && return 0
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    kill_process_tree "$child"
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

terminate_bless_desktop() {
  local bundle="$1"
  local bundle_id app_path=""
  bundle_id="$(derive_bundle_id "$bundle" 2>/dev/null || true)"
  app_path="/Applications/${bundle}.app"

  if [[ -n "$bundle_id" ]]; then
    osascript -e "tell application id \"$bundle_id\" to quit" 2>/dev/null \
      || osascript -e "quit app id \"$bundle_id\"" 2>/dev/null \
      || true
  fi

  if [[ -d "$app_path" ]]; then
    pkill -f "$app_path" 2>/dev/null || true
  fi

  if [[ -n "$DESKTOP_LAUNCH_PID" ]]; then
    kill_process_tree "$DESKTOP_LAUNCH_PID"
    wait "$DESKTOP_LAUNCH_PID" 2>/dev/null || true
  fi

  if [[ -n "$WORKTREE" && -d "$WORKTREE" ]]; then
    pkill -f "$WORKTREE/desktop/macos/run.sh" 2>/dev/null || true
  fi

  sleep 0.5

  if pgrep -f "$app_path" >/dev/null 2>&1; then
    echo "bless cleanup: ${bundle}.app still running; sending SIGKILL" >&2
    pkill -9 -f "$app_path" 2>/dev/null || true
  fi
  if [[ -n "$bundle_id" ]] && pgrep -f "$bundle_id" >/dev/null 2>&1; then
    pkill -9 -f "$bundle_id" 2>/dev/null || true
  fi
}

wait_for_bridge() {
  local port="$1"
  local deadline=$((SECONDS + BRIDGE_WAIT_SECS))
  while (( SECONDS < deadline )); do
    if python3 - "$port" <<'PY'
import json
import sys
import urllib.error
import urllib.request

port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok"):
        raise SystemExit(0)
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
    pass
raise SystemExit(1)
PY
    then
      echo "automation bridge healthy on port $port"
      return 0
    fi
    if [[ -n "$DESKTOP_LAUNCH_PID" ]] && ! kill -0 "$DESKTOP_LAUNCH_PID" 2>/dev/null; then
      echo "bless failed: desktop launch process exited before bridge became healthy" >&2
      return 1
    fi
    sleep 5
  done
  echo "bless failed: automation bridge not healthy within ${BRIDGE_WAIT_SECS}s (port $port)" >&2
  return 1
}

cleanup() {
  local exit_code=$?
  if [[ -n "$BUNDLE" ]]; then
    terminate_bless_desktop "$BUNDLE"
  elif [[ -n "$DESKTOP_LAUNCH_PID" ]]; then
    kill_process_tree "$DESKTOP_LAUNCH_PID"
    wait "$DESKTOP_LAUNCH_PID" 2>/dev/null || true
  fi
  if [[ "$KEEP_STACK" -eq 0 && -d "$WORKTREE" ]]; then
    (cd "$WORKTREE" && PROVIDER_MODE=offline make dev-down) >/dev/null 2>&1 || true
  fi
  if [[ "$BLESS_SUCCESS" -eq 1 ]]; then
    rm -rf "$WORKTREE"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

(
  cd "$WORKTREE"
  PROVIDER_MODE=offline make dev-up
  make desktop-run-local DESKTOP_APP_NAME="$BUNDLE" DESKTOP_USER=alice
) >"$LAUNCH_LOG" 2>&1 &
DESKTOP_LAUNCH_PID=$!

if ! wait_for_bridge "$AUTOMATION_PORT"; then
  echo "--- last 80 lines of $LAUNCH_LOG ---" >&2
  tail -n 80 "$LAUNCH_LOG" >&2 || true
  exit 1
fi

(
  cd "$WORKTREE/desktop/macos"
  ./scripts/desktop-core-harness.sh --tier 2 --bundle "$BUNDLE" --port "$AUTOMATION_PORT" --keep-stack
)

EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/* 2>/dev/null | head -1)
if [[ -z "$EVIDENCE" || ! -f "$EVIDENCE/manifest.json" ]]; then
  echo "bless failed: missing harness evidence" >&2
  exit 1
fi

if ! python3 "$KEYVALUE_PY" check-manifest "$EVIDENCE/manifest.json"; then
  echo "bless failed: tier 2 harness did not pass; evidence: $EVIDENCE" >&2
  exit 1
fi

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ASSET="bless-evidence-${VERSION}-$(date -u +%Y%m%dT%H%M%SZ).json"
cp "$EVIDENCE/manifest.json" "/tmp/$ASSET"

BODY_FILE=/tmp/bless-release-body.md
gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json body --jq .body > "$BODY_FILE"

python3 "$KEYVALUE_PY" update-blessed "$BODY_FILE" "$STAMP" "$SHA" "$ASSET"

gh release upload "$RELEASE_TAG" "/tmp/$ASSET" --repo BasedHardware/omi --clobber
gh release edit "$RELEASE_TAG" --repo BasedHardware/omi --notes-file "$BODY_FILE"

BLESS_SUCCESS=1
echo "Blessed $RELEASE_TAG at $SHA (evidence asset: $ASSET, automation port: $AUTOMATION_PORT)"
