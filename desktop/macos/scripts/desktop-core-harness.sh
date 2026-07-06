#!/usr/bin/env bash
# Desktop Core E2E harness — tiered dispatcher over existing runners.
#
# Usage:
#   ./scripts/desktop-core-harness.sh --self-check
#   ./scripts/desktop-core-harness.sh --tier 0
#   ./scripts/desktop-core-harness.sh --tier 1 --bundle omi-core-e2e
#   ./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e --keep-stack
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
HARNESS_ROOT="$DESKTOP_DIR/.harness/desktop-core"

TIER=""
BUNDLE="${OMI_CORE_E2E_BUNDLE:-omi-core-e2e}"
KEEP_STACK=0
SELF_CHECK=0
PORT="${OMI_AUTOMATION_PORT:-47777}"

usage() {
  cat <<'USAGE'
Desktop core E2E harness.

Options:
  --tier N          Run tier N checks (0-3). Required unless --self-check.
  --bundle NAME     Named test bundle for T1+ (default: omi-core-e2e)
  --port PORT       Automation bridge port (default: OMI_AUTOMATION_PORT or 47777)
  --keep-stack      On T2+, leave dev-up running after the run
  --self-check      Linux-safe static checks only (flow lint + gauntlet self-check)
  --help            Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier)
      TIER="${2:?--tier requires a value}"
      shift
      ;;
    --bundle)
      BUNDLE="${2:?--bundle requires a value}"
      shift
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift
      ;;
    --keep-stack)
      KEEP_STACK=1
      ;;
    --self-check)
      SELF_CHECK=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

run_id() {
  date -u +%Y%m%dT%H%M%SZ
}

git_sha() {
  git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown
}

finalize_run() {
  local run_dir="$1"
  local passed="$2"
  local tier_value="$3"
  local started_at="$4"
  local duration_s="$5"
  local flows_json="$6"
  python3 - "$run_dir/manifest.json" "$passed" "$tier_value" "$started_at" "$duration_s" "$flows_json" "$BUNDLE" "$(git_sha)" <<'PY'
import json
import sys
from pathlib import Path

path, passed, tier_value, started_at, duration_s, flows_json, bundle, git_sha = sys.argv[1:9]
manifest = {
    "passed": passed == "true",
    "tier": int(tier_value) if tier_value.isdigit() else tier_value,
    "git_sha": git_sha,
    "bundle": bundle,
    "started_at": started_at,
    "duration_s": float(duration_s),
    "flows": json.loads(flows_json or "[]"),
}
Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  if [[ "$passed" == "true" ]]; then
    ln -sfn "$(basename "$run_dir")" "$HARNESS_ROOT/latest-green"
  fi
  {
    echo "# Desktop Core E2E"
    echo ""
    echo "- tier: ${tier_value}"
    echo "- bundle: ${BUNDLE}"
    echo "- passed: ${passed}"
    echo "- duration_s: ${duration_s}"
    echo "- evidence: ${run_dir}"
  } >"$run_dir/summary.md"
}

run_self_check() {
  echo "=== desktop-core-harness self-check ==="
  python3 "$SCRIPT_DIR/desktop-flow-lint.py"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    python3 "$SCRIPT_DIR/agent-continuity-gauntlet-lib.py" --self-check
  else
    python3 "$SCRIPT_DIR/agent-continuity-gauntlet-lib.py" --self-check
  fi
  if [[ -x "$REPO_ROOT/backend/test-preflight.sh" ]]; then
    bash "$REPO_ROOT/backend/test-preflight.sh" >/dev/null
  fi
  python3 -m pytest "$REPO_ROOT/backend/testing/contracts" -q --maxfail=1 -k "desktop" 2>/dev/null \
    || python3 -m pytest "$REPO_ROOT/backend/testing/contracts" -q --maxfail=1
  echo "desktop-core-harness self-check passed"
}

flow_tier() {
  local flow_path="$1"
  python3 - "$flow_path" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
flow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
tier = flow.get("tier")
if tier == "manual":
    print("manual")
elif tier is None:
    print("missing")
else:
    print(int(tier))
PY
}

flows_for_max_tier() {
  local max_tier="$1"
  python3 - "$DESKTOP_DIR/e2e/flows" "$max_tier" <<'PY'
import sys
from pathlib import Path
import yaml

flows_dir = Path(sys.argv[1])
max_tier = int(sys.argv[2])
for path in sorted(flows_dir.glob("*.yaml")):
    flow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tier = flow.get("tier")
    if tier == "manual":
        continue
    if tier is None:
        continue
    if int(tier) <= max_tier:
        print(path)
PY
}

refuse_prod_bundle() {
  local bundle="$1"
  case "$bundle" in
    Omi|Omi\ Beta|"Omi Dev")
      echo "desktop-core-harness: refusing prod/dev shared bundle name: $bundle" >&2
      exit 1
      ;;
  esac
  if [[ "$bundle" != omi-* ]]; then
    echo "desktop-core-harness: bundle must be omi-* named test bundle, got: $bundle" >&2
    exit 1
  fi
}

bridge_health() {
  python3 - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
if not payload.get("ok"):
    raise SystemExit(f"bridge unhealthy: {payload}")
PY
}

ensure_dev_stack() {
  if make -C "$REPO_ROOT" dev-status >/dev/null 2>&1; then
    :
  else
    PROVIDER_MODE=offline make -C "$REPO_ROOT" dev-up
  fi
}

if [[ "$SELF_CHECK" -eq 1 ]]; then
  run_self_check
  exit 0
fi

if [[ -z "$TIER" ]]; then
  echo "--tier is required unless --self-check" >&2
  usage >&2
  exit 2
fi

RUN_DIR="$HARNESS_ROOT/$(run_id)-t${TIER}"
mkdir -p "$RUN_DIR"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_SEC=$(date +%s)
FLOW_RESULTS="[]"
PASSED=true

case "$TIER" in
  0)
  run_self_check
  ;;
  1|2|3)
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "desktop-core-harness: tier $TIER requires macOS" >&2
    exit 1
  fi
  refuse_prod_bundle "$BUNDLE"
  if [[ "$TIER" -ge 2 ]]; then
    ensure_dev_stack
  fi
  bridge_health || {
    echo "desktop-core-harness: start bundle first, e.g. OMI_APP_NAME=$BUNDLE ./run.sh" >&2
    exit 1
  }
  mapfile -t FLOW_PATHS < <(flows_for_max_tier "$TIER")
  if [[ "$TIER" -eq 1 ]]; then
    FLOW_PATHS=(
      "$DESKTOP_DIR/e2e/flows/harness-smoke.yaml"
      "$DESKTOP_DIR/e2e/flows/navigation.yaml"
    )
  fi
  for flow_path in "${FLOW_PATHS[@]}"; do
  [[ -f "$flow_path" ]] || continue
  flow_name="$(basename "$flow_path" .yaml)"
  echo "=== flow: $flow_name ==="
  flow_out="$RUN_DIR/flows/$flow_name"
  mkdir -p "$flow_out"
  set +e
  (
    cd "$DESKTOP_DIR"
    python3 scripts/omi-harness run "$flow_path" --lane bridge --port "$PORT" --out "$flow_out" \
      --allow-legacy-flow-version
  )
  flow_status=$?
  set -e
  if [[ "$flow_status" -ne 0 ]]; then
    PASSED=false
  fi
  FLOW_RESULTS=$(python3 - "$FLOW_RESULTS" "$flow_name" "$flow_status" "$flow_out" <<'PY'
import json
import sys
from pathlib import Path

rows = json.loads(sys.argv[1])
name, status, out_dir = sys.argv[2:5]
rows.append({
    "name": name,
    "passed": int(status) == 0,
    "artifacts": str(Path(out_dir).resolve()),
})
print(json.dumps(rows))
PY
)
  done
  if [[ "$TIER" -ge 2 ]]; then
    set +e
    "$SCRIPT_DIR/spatial-overlay-harness.sh" --swift-only
    overlay_status=$?
    set -e
    if [[ "$overlay_status" -ne 0 ]]; then
      PASSED=false
    fi
    FLOW_RESULTS=$(python3 - "$FLOW_RESULTS" "spatial-overlay-swift" "$overlay_status" "$DESKTOP_DIR/.harness/spatial-overlay" <<'PY'
import json
import sys
rows = json.loads(sys.argv[1])
name, status, out_dir = sys.argv[2:5]
rows.append({"name": name, "passed": int(status) == 0, "artifacts": out_dir})
print(json.dumps(rows))
PY
)
  fi
  if [[ "$TIER" -eq 3 ]]; then
    set +e
    OMI_AUTOMATION_PORT="$PORT" "$SCRIPT_DIR/agent-continuity-gauntlet.sh" --bundle-id "com.omi.${BUNDLE#omi-}"
    gauntlet_status=$?
    set -e
    if [[ "$gauntlet_status" -ne 0 ]]; then
      PASSED=false
    fi
    FLOW_RESULTS=$(python3 - "$FLOW_RESULTS" "agent-continuity-gauntlet" "$gauntlet_status" "$DESKTOP_DIR/.harness/agent-continuity-gauntlet" <<'PY'
import json
import sys
rows = json.loads(sys.argv[1])
name, status, out_dir = sys.argv[2:5]
rows.append({"name": name, "passed": int(status) == 0, "artifacts": out_dir})
print(json.dumps(rows))
PY
)
  fi
  if [[ "$KEEP_STACK" -eq 0 && "$TIER" -ge 2 ]]; then
    make -C "$REPO_ROOT" dev-down >/dev/null 2>&1 || true
  fi
  ;;
  *)
  echo "invalid tier: $TIER" >&2
  exit 2
  ;;
esac

DURATION=$(( $(date +%s) - START_SEC ))
if [[ "$PASSED" == true ]]; then
  finalize_run "$RUN_DIR" true "$TIER" "$STARTED_AT" "$DURATION" "$FLOW_RESULTS"
  echo "desktop-core-harness tier $TIER passed (evidence: $RUN_DIR)"
  exit 0
fi

finalize_run "$RUN_DIR" false "$TIER" "$STARTED_AT" "$DURATION" "$FLOW_RESULTS"
echo "desktop-core-harness tier $TIER failed (evidence: $RUN_DIR)" >&2
exit 1
