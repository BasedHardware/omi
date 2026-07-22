#!/usr/bin/env bash
# Desktop Core E2E harness — tiered dispatcher over existing runners.
#
# Usage:
#   ./scripts/desktop-core-harness.sh --self-check
#   ./scripts/desktop-core-harness.sh --self-check --skip-backend-contracts
#   ./scripts/desktop-core-harness.sh --tier 0
#   ./scripts/desktop-core-harness.sh --tier 1 --bundle omi-core-e2e
#   ./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e --keep-stack
#   ./scripts/desktop-core-harness.sh --readiness
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
HARNESS_ROOT="$DESKTOP_DIR/.harness/desktop-core"

TIER=""
BUNDLE="${OMI_CORE_E2E_BUNDLE:-omi-core-e2e}"
FAULT_SUITE=0
FAULT_BUNDLE="omi-fault"
KEEP_STACK=0
SELF_CHECK=0
READINESS=0
SKIP_BACKEND_CONTRACTS=0
PORT="${OMI_AUTOMATION_PORT:-47777}"
DEV_STACK_PROVIDER_MODE=""

usage() {
  cat <<'USAGE'
Desktop core E2E harness.

Options:
  --tier N                    Run tier N checks (0-3). Required unless --self-check or --readiness.
  --bundle NAME               Named test bundle for T1+ (default: omi-core-e2e)
  --port PORT                 Automation bridge port (default: OMI_AUTOMATION_PORT or 47777)
  --keep-stack                On T2+, leave dev-up running after the run
  --fault-suite               Start omi-fault-inject + omi-fault bundle; run chat-fault-5xx flow
  --self-check                Static checks (flow lint + gauntlet self-check; backend contracts locally)
  --readiness                 Pre-tag readiness: self-check + offline dev-stack probe (no app launch, no E2E flows)
  --skip-backend-contracts    With --self-check, skip backend preflight + pytest contracts (CI desktop gate)
  --help                      Show this help
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
    --fault-suite)
      FAULT_SUITE=1
      ;;
    --self-check)
      SELF_CHECK=1
      ;;
    --readiness)
      READINESS=1
      ;;
    --skip-backend-contracts)
      SKIP_BACKEND_CONTRACTS=1
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
  python3 - "$run_dir/manifest.json" "$passed" "$tier_value" "$started_at" "$duration_s" "$flows_json" "$BUNDLE" "$(git_sha)" "$DEV_STACK_PROVIDER_MODE" <<'PY'
import json
import os
import sys
from pathlib import Path

path, passed, tier_value, started_at, duration_s, flows_json, bundle, git_sha, provider_mode = sys.argv[1:10]
manifest = {
    "passed": passed == "true",
    "tier": int(tier_value) if tier_value.isdigit() else tier_value,
    "git_sha": git_sha,
    "bundle": bundle,
    "started_at": started_at,
    "duration_s": float(duration_s),
    "flows": json.loads(flows_json or "[]"),
}
if provider_mode:
    manifest["provider_mode"] = provider_mode
lane = os.environ.get("OMI_READINESS_LANE")
if lane:
    manifest["lane"] = lane
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
    if [[ -n "$DEV_STACK_PROVIDER_MODE" ]]; then
      echo "- provider_mode: ${DEV_STACK_PROVIDER_MODE}"
    fi
    echo "- passed: ${passed}"
    echo "- duration_s: ${duration_s}"
    echo "- evidence: ${run_dir}"
  } >"$run_dir/summary.md"
}

run_self_check() {
  echo "=== desktop-core-harness self-check ==="
  python3 "$SCRIPT_DIR/desktop-flow-lint.py"
  python3 "$SCRIPT_DIR/agent-continuity-gauntlet-lib.py" --self-check
  if [[ "$SKIP_BACKEND_CONTRACTS" -eq 1 ]]; then
    echo "desktop-core-harness: skipping backend preflight + pytest contracts (--skip-backend-contracts; CI desktop gate)"
    echo "desktop-core-harness self-check passed (desktop static checks only)"
    return 0
  fi
  if [[ -x "$REPO_ROOT/backend/test-preflight.sh" ]]; then
    bash "$REPO_ROOT/backend/test-preflight.sh" >/dev/null
  fi
  python3 -m pytest "$REPO_ROOT/backend/testing/contracts" -q --maxfail=1 -k "desktop" 2>/dev/null \
    || python3 -m pytest "$REPO_ROOT/backend/testing/contracts" -q --maxfail=1
  echo "desktop-core-harness self-check passed"
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
    if tier == "manual" or tier == "fault":
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

maybe_teardown_dev_stack() {
  if [[ "$KEEP_STACK" -eq 0 && ( "${TIER:-0}" -ge 2 || "${READINESS:-0}" -eq 1 ) ]]; then
    make -C "$REPO_ROOT" dev-down >/dev/null 2>&1 || true
  fi
}

bridge_health() {
  local expected_bundle_id
  # shellcheck source=app-config.sh
  source "$SCRIPT_DIR/app-config.sh"
  derive_omi_app_config "$BUNDLE"
  expected_bundle_id="$BUNDLE_ID"
  python3 - "$PORT" "$expected_bundle_id" <<'PY'
import json
import sys
import urllib.request

port, expected = sys.argv[1:3]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
if not payload.get("ok"):
    raise SystemExit(f"bridge unhealthy: {payload}")
actual = payload.get("bundleIdentifier")
if actual != expected:
    raise SystemExit(f"wrong bundle on port {port}: expected {expected}, got {actual}")
PY
}

# Like bridge_health, but also requires the /health bundleIdentifier to match the
# expected fault bundle — prevents running fault flows against a stale dev stack
# already listening on $PORT.
verify_fault_bundle_health() {
  local port="$1"
  local expected_bundle="$2"
  python3 - "$port" "$expected_bundle" <<'PY'
import json
import sys
import urllib.request

port, expected = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
if not payload.get("ok"):
    raise SystemExit(f"bridge unhealthy: {payload}")
actual = payload.get("bundleIdentifier")
if actual != expected:
    raise SystemExit(f"wrong bundle on port {port}: expected {expected}, got {actual}")
PY
}

# Probe dev-harness stack health + provider_mode from config-digest.json.
# Exit 0: healthy offline stack owned by this worktree/instance (JSON on stdout)
# Exit 1: stack not up / unhealthy / foreign (caller may dev-up)
# Exit 2: config digest reports non-offline provider_mode (T2 must abort)
probe_dev_stack() {
  python3 - "$REPO_ROOT" <<'PY'
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "scripts" / "dev-harness"))
from dev_harness import config, safety

# Services with process records in the dev-harness manifest. The Firebase Auth
# emulator has no record of its own — it runs inside the "firestore" process
# (firebase emulators:start --only firestore,auth); auth liveness is covered by
# the firestore PID plus the auth HTTP health check below. Typesense's record is
# the harness supervise wrapper around `docker run`, so alive-PID + ownership
# marker semantics hold for it like any other service.
REQUIRED_SERVICES = (
    "firestore",
    "redis",
    "typesense",
    "backend",
    "desktop-backend",
)


def http_ok(url: str, headers: dict[str, str] | None = None, timeout: float = 1.0) -> bool:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except Exception:
        return False


def load_process_records(cfg: config.HarnessConfig) -> list[dict[str, object]]:
    manifest_path = cfg.layout.process_manifest
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    records = manifest.get("processes") if isinstance(manifest, dict) else None
    return records if isinstance(records, list) else []


def service_record(records: list[dict[str, object]], service: str) -> dict[str, object] | None:
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("service") != service:
            continue
        pid = int(record.get("pid", -1))
        if safety.process_exists(pid):
            return record
    return None


def ownership_failure(
    reason: str,
    *,
    provider_mode: str | None,
    digest_path: Path,
    details: object | None = None,
) -> None:
    payload: dict[str, object] = {
        "healthy": False,
        "provider_mode": provider_mode,
        "reason": reason,
        "config_digest_path": str(digest_path),
    }
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload))
    raise SystemExit(1)


cfg = config.load_config(repo_root)
digest_path = cfg.layout.config_digest_path
digest: dict[str, object] = {}
if digest_path.is_file():
    try:
        loaded = json.loads(digest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        loaded = {}
    if isinstance(loaded, dict):
        digest = loaded

provider_mode = digest.get("provider_mode")
if isinstance(provider_mode, str) and provider_mode.strip():
    provider_mode = provider_mode.strip()
else:
    provider_mode = None

if not cfg.layout.sentinel_path.is_file():
    ownership_failure("missing_sentinel", provider_mode=provider_mode, digest_path=digest_path)

try:
    safety.read_and_validate_sentinel(
        cfg.layout.state_root,
        repo_root=cfg.repo_root,
        instance=cfg.instance,
    )
except safety.SafetyError as exc:
    ownership_failure(
        "sentinel_invalid",
        provider_mode=provider_mode,
        digest_path=digest_path,
        details=str(exc),
    )

if not digest_path.is_file():
    ownership_failure("missing_config_digest", provider_mode=provider_mode, digest_path=digest_path)

if digest.get("instance") != cfg.instance:
    ownership_failure(
        "digest_instance_mismatch",
        provider_mode=provider_mode,
        digest_path=digest_path,
        details={"expected": cfg.instance, "got": digest.get("instance")},
    )

expected_state_root = str(cfg.layout.state_root)
if str(digest.get("state_root", "")) != expected_state_root:
    ownership_failure(
        "digest_state_root_mismatch",
        provider_mode=provider_mode,
        digest_path=digest_path,
        details={"expected": expected_state_root, "got": digest.get("state_root")},
    )

if provider_mode and provider_mode != "offline":
    print(
        json.dumps(
            {
                "healthy": False,
                "provider_mode": provider_mode,
                "reason": "non_offline_provider_mode",
                "config_digest_path": str(digest_path),
            }
        )
    )
    raise SystemExit(2)

records = load_process_records(cfg)
missing_services: list[str] = []
for service in REQUIRED_SERVICES:
    record = service_record(records, service)
    if record is None:
        missing_services.append(service)
        continue
    pid = int(record["pid"])
    try:
        safety.validate_owned_pid(
            pid,
            process_manifest=cfg.layout.process_manifest,
            service=service,
        )
    except safety.SafetyError as exc:
        missing_services.append(f"{service}:{exc}")
        continue
    if service == "typesense":
        container = f"omi-dev-harness-{cfg.instance}-typesense"
        container_running = subprocess.run(
            ["docker", "ps", "--filter", f"name={container}", "--filter", "status=running", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        ).stdout.strip()
        if not container_running:
            missing_services.append(f"{service}:container-not-running")

if missing_services:
    ownership_failure(
        "stale_or_missing_process_records",
        provider_mode=provider_mode,
        digest_path=digest_path,
        details=missing_services,
    )

typesense_headers = {"X-TYPESENSE-API-KEY": config.LOCAL_TYPESENSE_API_KEY}
checks = {
    "firestore": f"http://{cfg.firestore_host}/",
    "auth": f"http://{cfg.auth_host}/",
    "typesense": f"http://127.0.0.1:{config.TYPESENSE_PORT}/collections",
    "backend": f"{cfg.backend_url}/docs",
    "desktop-backend": f"{cfg.desktop_backend_url}/health",
}
failures: list[str] = []
for service, url in checks.items():
    headers = typesense_headers if service == "typesense" else None
    if not http_ok(url, headers=headers):
        failures.append(service)

if failures:
    print(
        json.dumps(
            {
                "healthy": False,
                "provider_mode": provider_mode,
                "reason": "health_check_failed",
                "failures": failures,
                "config_digest_path": str(digest_path),
            }
        )
    )
    raise SystemExit(1)

if provider_mode != "offline":
    print(
        json.dumps(
            {
                "healthy": False,
                "provider_mode": provider_mode,
                "reason": "missing_offline_digest",
                "config_digest_path": str(digest_path),
            }
        )
    )
    raise SystemExit(1)

print(
    json.dumps(
        {
            "healthy": True,
            "provider_mode": provider_mode,
            "config_digest_path": str(digest_path),
            "instance": cfg.instance,
            "state_root": expected_state_root,
        }
    )
)
PY
}

ensure_dev_stack() {
  local probe_json probe_status attempt
  set +e
  probe_json="$(probe_dev_stack)"
  probe_status=$?
  set -e

  if [[ "$probe_status" -eq 0 ]]; then
    DEV_STACK_PROVIDER_MODE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["provider_mode"])' "$probe_json")"
    echo "desktop-core-harness: dev stack healthy (provider_mode=${DEV_STACK_PROVIDER_MODE})"
    return 0
  fi

  if [[ "$probe_status" -eq 2 ]]; then
    echo "desktop-core-harness: refusing T2+ run — dev stack provider_mode is not offline" >&2
    echo "$probe_json" >&2
    echo "Run 'make dev-down' then retry with PROVIDER_MODE=offline make dev-up" >&2
    exit 1
  fi

  echo "desktop-core-harness: dev stack not healthy; starting with PROVIDER_MODE=offline"
  echo "$probe_json"
  PROVIDER_MODE=offline make -C "$REPO_ROOT" dev-up

  for attempt in $(seq 1 15); do
    set +e
    probe_json="$(probe_dev_stack)"
    probe_status=$?
    set -e
    if [[ "$probe_status" -eq 0 ]]; then
      DEV_STACK_PROVIDER_MODE="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["provider_mode"])' "$probe_json")"
      echo "desktop-core-harness: dev stack ready (provider_mode=${DEV_STACK_PROVIDER_MODE})"
      return 0
    fi
    if [[ "$probe_status" -eq 2 ]]; then
      echo "desktop-core-harness: dev stack provider_mode is not offline after dev-up" >&2
      echo "$probe_json" >&2
      exit 1
    fi
    if [[ "$attempt" -lt 15 ]]; then
      sleep 2
    fi
  done

  echo "desktop-core-harness: dev stack still unhealthy after dev-up" >&2
  echo "$probe_json" >&2
  exit 1
}

FAULT_RUN_PID=""
FAULT_RUN_STARTED=0

stop_fault_stack() {
  if [[ "$FAULT_RUN_STARTED" -eq 1 ]]; then
    if [[ -n "$FAULT_RUN_PID" ]]; then
      kill "$FAULT_RUN_PID" 2>/dev/null || true
      wait "$FAULT_RUN_PID" 2>/dev/null || true
      FAULT_RUN_PID=""
    fi
    pkill -f "${FAULT_BUNDLE}.app" 2>/dev/null || true
    FAULT_RUN_STARTED=0
  fi
  if [[ -x "$SCRIPT_DIR/omi-fault-inject.sh" ]]; then
    "$SCRIPT_DIR/omi-fault-inject.sh" stop >/dev/null 2>&1 || true
  fi
}

start_fault_stack() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "desktop-core-harness: --fault-suite requires macOS" >&2
    exit 1
  fi
  refuse_prod_bundle "$FAULT_BUNDLE"
  "$SCRIPT_DIR/omi-fault-inject.sh" stop >/dev/null 2>&1 || true
  eval "$("$SCRIPT_DIR/omi-fault-inject.sh" start error)"
  echo "desktop-core-harness: fault inject at $OMI_FAULT_URL"
  # Auth seed runs inside ./run.sh after install (passes APP_PATH for Keychain ACL).
  # Do not pre-seed here — without the installed .app path, seed refuses to write tokens.
  (
    cd "$DESKTOP_DIR"
    OMI_DESKTOP_LOCAL_PROFILE=1 \
      OMI_HARNESS_INSTANCE="${OMI_HARNESS_INSTANCE:-${OMI_LOCAL_INSTANCE:-fault-suite}}" \
      OMI_SKIP_AUTH_SEED=1 \
      OMI_SKIP_SETTINGS_SEED=1 \
      OMI_LOCAL_PROFILE_STORAGE_NAME="$FAULT_BUNDLE" \
      OMI_LOCAL_AUTH_USER=alice \
      OMI_LOCAL_AUTH_EMAIL=alice@local.omi.invalid \
      OMI_LOCAL_AUTH_PASSWORD=alice-local-password-030 \
      OMI_LOCAL_AUTH_DISPLAY_NAME='Synthetic Alice' \
      FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
      FIREBASE_PROJECT_ID=demo-omi-local \
      FIREBASE_AUTH_PROJECT_ID=demo-omi-local \
      FIRESTORE_DATABASE_ID='(default)' \
      FIREBASE_API_KEY=local-firebase-auth-emulator-api-key \
      OMI_ALLOW_ADHOC_SIGN=1 \
      OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 \
      OMI_PYTHON_API_URL="$OMI_FAULT_URL" \
      OMI_DESKTOP_API_URL="$OMI_FAULT_URL" \
      OMI_AUTH_API_URL="$OMI_FAULT_URL" \
      OMI_FAULT_MODEL_AUTH_TOKEN=omi-fault-model-token \
      OMI_AUTOMATION_PORT="$PORT" \
      OMI_APP_NAME="$FAULT_BUNDLE" \
      ./run.sh
  ) &
  FAULT_RUN_PID=$!
  FAULT_RUN_STARTED=1
  local expected_bundle="com.omi.${FAULT_BUNDLE}"
  local attempt
  for attempt in $(seq 1 90); do
    if verify_fault_bundle_health "$PORT" "$expected_bundle" 2>/dev/null; then
      OMI_AUTOMATION_PORT="$PORT" "$SCRIPT_DIR/omi-ctl" wait-ready 90
      echo "desktop-core-harness: $FAULT_BUNDLE bridge ready on port $PORT (bundle: $expected_bundle)"
      return 0
    fi
    if ! kill -0 "$FAULT_RUN_PID" 2>/dev/null; then
      echo "desktop-core-harness: $FAULT_BUNDLE launch exited before bridge was ready" >&2
      stop_fault_stack
      exit 1
    fi
    sleep 2
  done
  echo "desktop-core-harness: timed out waiting for $FAULT_BUNDLE bridge on port $PORT" >&2
  stop_fault_stack
  exit 1
}

run_flow_file() {
  local flow_path="$1"
  local run_dir="$2"
  [[ -f "$flow_path" ]] || return 0
  local flow_name flow_out flow_status
  flow_name="$(basename "$flow_path" .yaml)"
  echo "=== flow: $flow_name ==="
  flow_out="$run_dir/flows/$flow_name"
  mkdir -p "$flow_out"
  set +e
  (
    cd "$DESKTOP_DIR"
    python3 scripts/omi-harness run "$flow_path" --lane bridge --port "$PORT" --out "$flow_out" \
      --allow-legacy-flow-version
  )
  flow_status=$?
  set -e
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
  if [[ "$flow_status" -ne 0 ]]; then
    PASSED=false
  fi
}

if [[ "$SELF_CHECK" -eq 1 ]]; then
  run_self_check
  exit 0
fi

if [[ "$FAULT_SUITE" -eq 1 ]]; then
  RUN_DIR="$HARNESS_ROOT/$(run_id)-fault"
  mkdir -p "$RUN_DIR"
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  START_SEC=$(date +%s)
  FLOW_RESULTS="[]"
  PASSED=true
  trap stop_fault_stack EXIT
  start_fault_stack
  run_flow_file "$DESKTOP_DIR/e2e/flows/chat-fault-5xx.yaml" "$RUN_DIR"
  stop_fault_stack
  trap - EXIT
  DURATION=$(( $(date +%s) - START_SEC ))
  if [[ "$PASSED" == true ]]; then
    finalize_run "$RUN_DIR" true "fault" "$STARTED_AT" "$DURATION" "$FLOW_RESULTS"
    echo "desktop-core-harness fault-suite passed (evidence: $RUN_DIR)"
    exit 0
  fi
  finalize_run "$RUN_DIR" false "fault" "$STARTED_AT" "$DURATION" "$FLOW_RESULTS"
  echo "desktop-core-harness fault-suite failed (evidence: $RUN_DIR)" >&2
  exit 1
fi
if [[ "$READINESS" -eq 1 ]]; then
  # Pre-tag readiness gate: validate the exact desktop source + bounded offline
  # dev stack on the trusted self-hosted M1 BEFORE an immutable tag is created.
  # Distinct from post-tag qualification: no app launch, no E2E flows, no signed
  # artifacts. provider_mode=offline is enforced by ensure_dev_stack (no prod).
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "desktop-core-harness: --readiness requires macOS (trusted self-hosted M1)" >&2
    exit 1
  fi
  RUN_DIR="$HARNESS_ROOT/$(run_id)-readiness"
  mkdir -p "$RUN_DIR"
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  START_SEC=$(date +%s)
  FLOW_RESULTS="[]"
  run_self_check
  ensure_dev_stack
  maybe_teardown_dev_stack
  DURATION=$(( $(date +%s) - START_SEC ))
  finalize_run "$RUN_DIR" true "readiness" "$STARTED_AT" "$DURATION" "$FLOW_RESULTS"
  echo "desktop-core-harness readiness passed (evidence: $RUN_DIR)"
  exit 0
fi

if [[ -z "$TIER" ]]; then
  echo "--tier is required unless --self-check, --readiness, or --fault-suite" >&2
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
    maybe_teardown_dev_stack
    exit 1
  }
  FLOW_PATHS=()
  while IFS= read -r flow_path; do
    [[ -n "$flow_path" ]] && FLOW_PATHS+=("$flow_path")
  done < <(flows_for_max_tier "$TIER")
  for flow_path in "${FLOW_PATHS[@]}"; do
  run_flow_file "$flow_path" "$RUN_DIR"
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
    OMI_AUTOMATION_PORT="$PORT" "$SCRIPT_DIR/agent-continuity-gauntlet.sh" --bundle-id "com.omi.${BUNDLE}"
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
    maybe_teardown_dev_stack
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
