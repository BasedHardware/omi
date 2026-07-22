#!/usr/bin/env bash
# Qualify a macOS desktop candidate by rebuilding the tag and running T2 core E2E.
#
# Usage:
#   ./scripts/qualify-desktop-beta.sh v11.0.0+11000-macos
#   ./scripts/qualify-desktop-beta.sh --keep-stack v11.0.0+11000-macos
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
KEYVALUE_PY="$SCRIPT_DIR/release-keyvalue.py"

KEEP_STACK=0
AUTOMATIC=0
SIGNED_SMOKE_RESULT=""
CANDIDATE_GATE_RESULT=""
GITHUB_ACTIONS_ARTIFACT=0
RELEASE_TAG=""

usage() {
  cat <<'USAGE'
Qualify a macOS desktop candidate (rebuild tag + T2 core E2E).

Usage:
  qualify-desktop-beta.sh [--keep-stack] [--automatic] [--github-actions-artifact] \
    [--signed-smoke-result PATH --candidate-gate-result PATH] <vX.Y.Z+BUILD-macos>

Options:
  --keep-stack   Leave dev-harness stack running on exit (default: make dev-down)
  --automatic    Run richer automatic gates and require this to remain the newest candidate
  --signed-smoke-result PATH  Codemagic signed-artifact smoke evidence (required with --automatic)
  --candidate-gate-result PATH  Digest-bound candidate gate evidence (required with --automatic)
  --github-actions-artifact  Leave trusted evidence publication to the workflow artifact
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-stack)
      KEEP_STACK=1
      shift
      ;;
    --automatic)
      AUTOMATIC=1
      shift
      ;;
    --signed-smoke-result)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--signed-smoke-result requires a path" >&2; exit 2; }
      SIGNED_SMOKE_RESULT="$2"
      shift 2
      ;;
    --candidate-gate-result)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--candidate-gate-result requires a path" >&2; exit 2; }
      CANDIDATE_GATE_RESULT="$2"
      shift 2
      ;;
    --github-actions-artifact)
      GITHUB_ACTIONS_ARTIFACT=1
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
if [[ "$AUTOMATIC" -eq 1 ]]; then
  [[ -f "$SIGNED_SMOKE_RESULT" ]] || { echo "automatic qualification requires --signed-smoke-result" >&2; exit 2; }
  [[ -f "$CANDIDATE_GATE_RESULT" ]] || { echo "automatic qualification requires --candidate-gate-result" >&2; exit 2; }
  python3 - "$RELEASE_TAG" "$SIGNED_SMOKE_RESULT" "$CANDIDATE_GATE_RESULT" <<'PY'
import json
import sys

release_tag, smoke_path, gate_path = sys.argv[1:]
smoke = json.load(open(smoke_path, encoding="utf-8"))
gate = json.load(open(gate_path, encoding="utf-8"))
if smoke.get("ok") is not True or smoke.get("release_tag") != release_tag:
    raise SystemExit("automatic qualification requires passing signed-smoke evidence for the release tag")
if gate.get("passed") is not True or gate.get("release_tag") != release_tag:
    raise SystemExit("automatic qualification requires passing candidate-gate evidence for the release tag")
PY
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "qualify-desktop-beta.sh requires macOS" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "qualify-desktop-beta.sh requires gh CLI" >&2
  exit 1
fi

VERSION="${RELEASE_TAG#v}"
VERSION="${VERSION%-macos}"
BUNDLE="omi-qualification-${VERSION}"
WORKTREE="$REPO_ROOT/.qualification-worktrees/$RELEASE_TAG"
LAUNCH_LOG=""
DESKTOP_LAUNCH_PID=""
QUALIFICATION_SUCCESS=0
BRIDGE_WAIT_SECS=900

gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json tagName,isDraft,isPrerelease,publishedAt,assets,body \
  > /tmp/desktop-qualification-release.json

python3 "$KEYVALUE_PY" preflight-release /tmp/desktop-qualification-release.json "$RELEASE_TAG"

SHA=$(git -C "$REPO_ROOT" rev-list -n1 "$RELEASE_TAG")

remove_registered_qualification_worktree() {
  if git -C "$REPO_ROOT" worktree list --porcelain | grep -Fxq "worktree $WORKTREE"; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE"
    git -C "$REPO_ROOT" worktree prune
  elif [[ -e "$WORKTREE" ]]; then
    echo "qualification failed: unregistered worktree path exists: $WORKTREE" >&2
    return 1
  fi
}

remove_registered_qualification_worktree
git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" "$RELEASE_TAG"

LAUNCH_LOG="$WORKTREE/.qualification-desktop-launch.log"

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

terminate_qualification_desktop() {
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
    echo "qualification cleanup: ${bundle}.app still running; sending SIGKILL" >&2
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
      echo "qualification failed: desktop launch process exited before bridge became healthy" >&2
      return 1
    fi
    sleep 5
  done
  echo "qualification failed: automation bridge not healthy within ${BRIDGE_WAIT_SECS}s (port $port)" >&2
  return 1
}

cleanup() {
  local exit_code=$?
  if [[ -n "$BUNDLE" ]]; then
    terminate_qualification_desktop "$BUNDLE"
  elif [[ -n "$DESKTOP_LAUNCH_PID" ]]; then
    kill_process_tree "$DESKTOP_LAUNCH_PID"
    wait "$DESKTOP_LAUNCH_PID" 2>/dev/null || true
  fi
  if [[ "$KEEP_STACK" -eq 0 && -d "$WORKTREE" ]]; then
    (cd "$WORKTREE" && PROVIDER_MODE=offline make dev-down) >/dev/null 2>&1 || true
  fi
  if [[ "$QUALIFICATION_SUCCESS" -eq 1 ]]; then
    remove_registered_qualification_worktree || \
      echo "qualification cleanup: retained unregistered worktree path: $WORKTREE" >&2
  fi
  exit "$exit_code"
}
trap cleanup EXIT

terminate_qualification_desktop "$BUNDLE"
"$SCRIPT_DIR/prepare-qualification-profile.sh" "$BUNDLE"

(
  cd "$WORKTREE"
  PROVIDER_MODE=offline make dev-up
  OMI_SKIP_SETTINGS_SEED=1 make desktop-run-local DESKTOP_APP_NAME="$BUNDLE" DESKTOP_USER=alice
) >"$LAUNCH_LOG" 2>&1 &
DESKTOP_LAUNCH_PID=$!
# Build time must not consume the desktop-launch readiness allowance.
SECONDS=0

if ! wait_for_bridge "$AUTOMATION_PORT"; then
  echo "--- last 80 lines of $LAUNCH_LOG ---" >&2
  tail -n 80 "$LAUNCH_LOG" >&2 || true
  exit 1
fi

(
  cd "$WORKTREE/desktop/macos"
  if [[ "$AUTOMATIC" -eq 1 ]]; then
    ./scripts/desktop-core-harness.sh --self-check --skip-backend-contracts
  fi
  ./scripts/desktop-core-harness.sh --tier 2 --bundle "$BUNDLE" --port "$AUTOMATION_PORT" --keep-stack
)

EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/* 2>/dev/null | head -1)
if [[ -z "$EVIDENCE" || ! -f "$EVIDENCE/manifest.json" ]]; then
  echo "qualification failed: missing harness evidence" >&2
  exit 1
fi

if ! python3 "$KEYVALUE_PY" check-manifest "$EVIDENCE/manifest.json"; then
  echo "qualification failed: tier 2 harness did not pass; evidence: $EVIDENCE" >&2
  exit 1
fi

FAULT_EVIDENCE=""
if [[ "$AUTOMATIC" -eq 1 ]]; then
  (
    cd "$WORKTREE/desktop/macos"
    ./scripts/desktop-core-harness.sh --fault-suite --port "$((AUTOMATION_PORT + 1))"
  )
  FAULT_EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/*-fault 2>/dev/null | head -1)
  if [[ -z "$FAULT_EVIDENCE" || ! -f "$FAULT_EVIDENCE/manifest.json" ]]; then
    echo "automatic qualification failed: missing fault-suite evidence" >&2
    exit 1
  fi
  python3 - "$FAULT_EVIDENCE/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if manifest.get("passed") is not True or manifest.get("tier") != "fault":
    raise SystemExit("automatic qualification failed: fault-suite manifest did not pass")
PY
fi

if [[ "$GITHUB_ACTIONS_ARTIFACT" -eq 1 ]]; then
  QUALIFICATION_SUCCESS=1
  echo "Qualified $RELEASE_TAG for beta; trusted workflow will publish immutable Actions evidence."
  exit 0
fi

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EVIDENCE_FILE="/tmp/qualification-evidence-${VERSION}-$$.json"
cp "$EVIDENCE/manifest.json" "$EVIDENCE_FILE"

if [[ "$AUTOMATIC" -eq 1 ]]; then
  git -C "$REPO_ROOT" fetch origin --tags --force
  LATEST_TAG=$(git -C "$REPO_ROOT" for-each-ref --count=1 --sort=-v:refname \
    --format='%(refname:strip=2)' 'refs/tags/v*-macos')
  if [[ "$LATEST_TAG" != "$RELEASE_TAG" ]]; then
    echo "automatic qualification stopped: newer candidate exists ($LATEST_TAG)" >&2
    exit 1
  fi
  python3 - "$EVIDENCE_FILE" "$SIGNED_SMOKE_RESULT" "$CANDIDATE_GATE_RESULT" "$FAULT_EVIDENCE/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

evidence_path, smoke_path, gate_path, fault_path = map(Path, sys.argv[1:5])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
evidence["qualification_mode"] = "automatic"
evidence["signed_artifact_smoke"] = json.loads(smoke_path.read_text(encoding="utf-8"))
evidence["candidate_gate"] = json.loads(gate_path.read_text(encoding="utf-8"))
evidence["fault_suite"] = json.loads(fault_path.read_text(encoding="utf-8"))
evidence["automatic_gates"] = ["signed-artifact", "static-self-check", "tier-2", "fault-suite"]
evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
fi

# Qualification evidence is factual, immutable history. Its content digest is
# part of the asset identity and uploads never clobber an earlier observation.
EVIDENCE_SHA=$(shasum -a 256 "$EVIDENCE_FILE" | awk '{print $1}')
ASSET="qualification-evidence-${VERSION}-${EVIDENCE_SHA}.json"
mv "$EVIDENCE_FILE" "/tmp/$ASSET"

BODY_FILE=/tmp/desktop-qualification-release-body.md
gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json body --jq .body > "$BODY_FILE"

python3 "$KEYVALUE_PY" update-qualified-beta "$BODY_FILE" "$STAMP" "$SHA" "$ASSET"

gh release upload "$RELEASE_TAG" "/tmp/$ASSET" --repo BasedHardware/omi
gh release edit "$RELEASE_TAG" --repo BasedHardware/omi --notes-file "$BODY_FILE"

QUALIFICATION_SUCCESS=1
echo "Qualified $RELEASE_TAG for beta at $SHA (evidence asset: $ASSET, automation port: $AUTOMATION_PORT)"
