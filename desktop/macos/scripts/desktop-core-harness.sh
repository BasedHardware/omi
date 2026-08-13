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
FAULT_PORT="${OMI_FAULT_PORT:-47790}"
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
  --readiness                 Pre-tag readiness: self-check + offline dev-stack probe; if a
                              launched named bundle is already listening on --port, also verify
                              automation /health identity + agent protocol readiness
                              (no app launch required; offline-only unit checks stay possible)
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
  # Hermetic /health identity+protocol contract. Skip under OMI_TEST_SCENARIO so
  # readiness teardown fixtures that stub python3 remain offline-only.
  if [[ -z "${OMI_TEST_SCENARIO:-}" ]]; then
    evaluate_bridge_health_payload "com.omi.omi-core-e2e" \
      '{"ok":true,"bundleIdentifier":"com.omi.omi-core-e2e","agentRuntimeRunning":true,"agentRuntimeExpectedProtocolVersion":3,"agentRuntimeProtocolVersion":3,"agentRuntimeVersion":"test"}' \
      --require-protocol >/dev/null
    if evaluate_bridge_health_payload "com.omi.omi-core-e2e" \
      '{"ok":true,"bundleIdentifier":"com.omi.omi-core-e2e","agentRuntimeRunning":true,"agentRuntimeExpectedProtocolVersion":3,"agentRuntimeProtocolVersion":2}' \
      --require-protocol >/dev/null 2>&1; then
      echo "desktop-core-harness: protocol mismatch fixture should fail" >&2
      exit 1
    fi
  fi
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

DEV_STACK_TEARDOWN_DONE=0

maybe_teardown_dev_stack() {
  if [[ "$DEV_STACK_TEARDOWN_DONE" -eq 1 ]]; then
    return 0
  fi
  if [[ "$KEEP_STACK" -eq 0 && ( "${TIER:-0}" -ge 2 || "${READINESS:-0}" -eq 1 ) ]]; then
    DEV_STACK_TEARDOWN_DONE=1
    make -C "$REPO_ROOT" dev-down >/dev/null 2>&1 || true
  fi
}

bridge_health() {
  local expected_bundle_id
  # shellcheck source=app-config.sh
  source "$SCRIPT_DIR/app-config.sh"
  derive_omi_app_config "$BUNDLE"
  expected_bundle_id="$BUNDLE_ID"
  evaluate_bridge_health_http "$PORT" "$expected_bundle_id" --require-protocol
}

# Evaluate an unauthenticated /health payload for bundle identity, and optionally
# negotiated agent-runtime protocol readiness. Shared by readiness + tier paths;
# hermetic callers can feed fixture JSON through evaluate_bridge_health_payload.
evaluate_bridge_health_payload() {
  local expected_bundle_id="$1"
  local health_json="$2"
  local require_protocol="${3:-}"
  python3 - "$expected_bundle_id" "$health_json" "$require_protocol" <<'PY'
import json
import sys

expected, raw, require_protocol = sys.argv[1:4]
payload = json.loads(raw)
if not payload.get("ok"):
    raise SystemExit(f"bridge unhealthy: {payload}")
actual = payload.get("bundleIdentifier")
if actual != expected:
    raise SystemExit(f"wrong bundle on port: expected {expected}, got {actual}")
if require_protocol == "--require-protocol":
    running = payload.get("agentRuntimeRunning")
    expected_proto = payload.get("agentRuntimeExpectedProtocolVersion")
    negotiated = payload.get("agentRuntimeProtocolVersion")
    if running is not True:
        raise SystemExit(f"agent runtime not running on bridge: {payload}")
    if not isinstance(expected_proto, int):
        raise SystemExit(f"missing agentRuntimeExpectedProtocolVersion: {payload}")
    if negotiated != expected_proto:
        raise SystemExit(
            f"agent protocol not ready: expected {expected_proto}, negotiated {negotiated}"
        )
    print(
        f"bridge health ok: bundleIdentifier={actual} "
        f"protocol={negotiated} runtime={payload.get('agentRuntimeVersion')}"
    )
else:
    print(f"bridge health ok: bundleIdentifier={actual}")
PY
}

evaluate_bridge_health_http() {
  local port="$1"
  local expected_bundle_id="$2"
  local require_protocol="${3:-}"
  local health_json
  health_json="$(python3 - "$port" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]
with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
    sys.stdout.write(response.read().decode("utf-8"))
PY
)"
  evaluate_bridge_health_payload "$expected_bundle_id" "$health_json" "$require_protocol"
}

# Like bridge_health identity check, but against an explicit fault bundle id —
# prevents running fault flows against a stale listener on $PORT. Fault inject
# fixtures only advertise ok+bundleIdentifier, so protocol is not required here.
verify_fault_bundle_health() {
  local port="$1"
  local expected_bundle="$2"
  evaluate_bridge_health_http "$port" "$expected_bundle"
}

automation_port_listening() {
  local port="$1"
  # Prefer bash /dev/tcp so hermetic readiness unit stubs that replace python3
  # cannot falsely report a listening bundle.
  if (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

# When --readiness finds a launched named bundle already bound to --port /
# OMI_AUTOMATION_PORT, verify identity + protocol. Offline-only unit checks leave
# the port closed and skip this path so they stay hermetic.
maybe_verify_readiness_bundle_health() {
  if ! automation_port_listening "$PORT"; then
    echo "desktop-core-harness: readiness skipping bundle /health (nothing listening on port $PORT)"
    return 0
  fi
  echo "desktop-core-harness: readiness verifying launched bundle /health on port $PORT (bundle=$BUNDLE)"
  bridge_health
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
    "llm-gateway",
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
        # Only the docker runtime has a container to cross-check; the native
        # typesense-server runtime is covered by the owned-PID check above.
        recorded_command = record.get("command") or []
        uses_docker = bool(recorded_command) and str(recorded_command[0]).endswith("docker")
        if uses_docker:
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
    "typesense": f"http://127.0.0.1:{cfg.typesense_port}/collections",
    "llm-gateway": f"{cfg.llm_gateway_url}/health",
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
  local probe_json probe_status attempt startup_attempt startup_attempt_limit dev_up_status
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
  startup_attempt_limit=1
  if [[ "$READINESS" -eq 1 && "$KEEP_STACK" -eq 0 ]]; then
    startup_attempt_limit=2
  fi

  for startup_attempt in $(seq 1 "$startup_attempt_limit"); do
    dev_up_status=0
    PROVIDER_MODE=offline make -C "$REPO_ROOT" dev-up || dev_up_status=$?

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
      if [[ "$dev_up_status" -ne 0 || "$attempt" -eq 15 ]]; then
        break
      fi
      sleep 2
    done

    if [[ "$startup_attempt" -lt "$startup_attempt_limit" ]]; then
      echo "desktop-core-harness: offline stack startup failed; cleaning owned state and retrying once" >&2
      echo "$probe_json" >&2
      make -C "$REPO_ROOT" dev-down
    fi
  done

  echo "desktop-core-harness: dev stack still unhealthy after dev-up" >&2
  echo "$probe_json" >&2
  exit 1
}

FAULT_RUN_PID=""
FAULT_RUN_STARTED=0
FAULT_RUN_TOKEN=""
FAULT_LAUNCH_TOKEN=""
FAULT_LAUNCH_SIGNAL_FILE=""
FAULT_APP_RECORD=""
FAULT_APP_LAUNCH_REQUESTED=0
FAULT_STATE_DIR=""
FAULT_RUN_DIR=""
FAULT_CLEANUP_DONE=0
FAULT_CLEANUP_STATUS=0
FAULT_FLOW_PID=""
FAULT_FLOW_RESULT_FILE=""

fault_token_for_run() {
  local token="${OMI_FAULT_RUN_TOKEN:-}"
  if [[ -z "$token" ]]; then
    token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  fi
  [[ "$token" =~ ^[A-Za-z0-9_-]{16,128}$ ]] || {
    echo "desktop-core-harness: invalid OMI_FAULT_RUN_TOKEN" >&2
    return 1
  }
  printf '%s\n' "$token"
}

fault_bundle_for_run() {
  local token="$1" slug
  slug="$(printf '%s' "$token" | tr '[:upper:]_' '[:lower:]-')"
  printf 'omi-fault-%s\n' "${slug:0:48}"
}

record_owned_fault_app() {
  local bundle_id app_path executable_path
  # shellcheck source=app-config.sh
  source "$SCRIPT_DIR/app-config.sh"
  derive_omi_app_config "$FAULT_BUNDLE"
  bundle_id="$BUNDLE_ID"
  app_path="/Applications/${FAULT_BUNDLE}.app"
  executable_path="$app_path/Contents/MacOS/Omi Computer"
  FAULT_APP_RECORD="$FAULT_RUN_DIR/fault-app.json"
  umask 077
  python3 - "$FAULT_APP_RECORD" "$FAULT_LAUNCH_SIGNAL_FILE" "$FAULT_RUN_TOKEN" "$FAULT_BUNDLE" "$bundle_id" "$app_path" "$executable_path" "$PORT" <<'PY'
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

path, signal_path, run_token, bundle, bundle_id, app_path, executable_path, port = sys.argv[1:]
signal = Path(signal_path)
if not signal.is_file() or signal.stat().st_uid != os.getuid() or stat.S_IMODE(signal.stat().st_mode) != 0o600:
    raise SystemExit("fault launch signal is missing or not owner-only")
fields = {}
for line in signal.read_text(encoding="utf-8").splitlines():
    if "=" not in line:
        raise SystemExit("fault launch signal is malformed")
    key, value = line.split("=", 1)
    if key in fields:
        raise SystemExit("fault launch signal has duplicate fields")
    fields[key] = value
expected_signal = {
    "schema_version": "1", "bundle_id": bundle_id, "app_path": app_path,
    "executable_path": executable_path, "launch_token": run_token,
}
if any(fields.get(key) != value for key, value in expected_signal.items()):
    raise SystemExit("fault launch signal does not bind this run")
if fields.get("launch_transport") not in {"open", "direct"}:
    raise SystemExit("fault launch signal has unknown transport")
proc = subprocess.run(["ps", "-axo", "pid=,lstart=,command="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
matches = []
for line in proc.stdout.splitlines():
    parts = line.split(None, 6)
    if len(parts) != 7 or not parts[0].isdigit():
        continue
    pid, started, command = int(parts[0]), " ".join(parts[1:6]), parts[6]
    try:
        argv = shlex.split(command)
    except ValueError:
        continue
    if executable_path in command and f"--omi-launch-token={run_token}" in command:
        matches.append((pid, started, command))
if len(matches) != 1:
    raise SystemExit(f"fault launch ownership is ambiguous (matching processes={len(matches)})")
pid, started, command = matches[0]
payload = {
    "schema_version": 2,
    "run_token": run_token,
    "bundle": bundle,
    "bundle_id": bundle_id,
    "app_path": app_path,
    "executable_path": executable_path,
    "automation_port": int(port),
    "launch_transport": fields["launch_transport"],
    "launch_pid": pid,
    "process_start": started,
    "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
}
target = Path(path)
target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
}

wait_for_fault_launch_signal() {
  local attempts="${OMI_FAULT_LAUNCH_SIGNAL_ATTEMPTS:-200}" attempt
  [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || {
    echo "desktop-core-harness: OMI_FAULT_LAUNCH_SIGNAL_ATTEMPTS must be a positive integer" >&2
    return 1
  }
  for attempt in $(seq 1 "$attempts"); do
    [[ -f "$FAULT_LAUNCH_SIGNAL_FILE" ]] && return 0
    sleep 0.05
  done
  echo "desktop-core-harness: timed out waiting for fault launch signal" >&2
  return 1
}

validated_fault_app_pid() {
  [[ -n "$FAULT_APP_RECORD" && -f "$FAULT_APP_RECORD" ]] || return 1
  python3 - "$FAULT_APP_RECORD" "$FAULT_RUN_TOKEN" "$FAULT_BUNDLE" "$PORT" <<'PY'
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

path, run_token, bundle, port = sys.argv[1:]
target = Path(path)
if target.stat().st_uid != os.getuid() or stat.S_IMODE(target.stat().st_mode) != 0o600:
    raise SystemExit("fault app record is not owner-only")
payload = json.loads(target.read_text(encoding="utf-8"))
expected = {
    "schema_version": 2,
    "run_token": run_token,
    "bundle": bundle,
    "bundle_id": f"com.omi.{bundle}",
    "app_path": f"/Applications/{bundle}.app",
    "executable_path": f"/Applications/{bundle}.app/Contents/MacOS/Omi Computer",
    "automation_port": int(port),
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit("fault app record does not bind this run")
if payload.get("launch_transport") not in {"open", "direct"}:
    raise SystemExit("fault app record has unknown launch transport")
if not isinstance(payload.get("launch_pid"), int) or payload["launch_pid"] <= 0 or not isinstance(payload.get("process_start"), str) or not isinstance(payload.get("command_sha256"), str):
    raise SystemExit("fault app record has no launch metadata")
pid = str(payload["launch_pid"])
proc = subprocess.run(["ps", "-p", pid, "-o", "lstart=,command="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
line = proc.stdout.strip()
if not line:
    raise SystemExit(3)  # known terminal state; no process can be signaled
parts = line.split(None, 5)
if len(parts) != 6:
    raise SystemExit("fault process metadata cannot be parsed")
started, command = " ".join(parts[:5]), parts[5]
try:
    argv = shlex.split(command)
except ValueError as exc:
    raise SystemExit(f"fault process command cannot be parsed: {exc}")
if started != payload["process_start"] or payload["executable_path"] not in command or f"--omi-launch-token={run_token}" not in command or hashlib.sha256(command.encode()).hexdigest() != payload["command_sha256"]:
    raise SystemExit("fault process no longer matches launch provenance")
print(pid)
PY
}

stop_recorded_fault_app() {
  local pid status attempt
  set +e
  pid="$(validated_fault_app_pid)"
  status=$?
  set -e
  if [[ "$status" -eq 3 ]]; then
    echo "desktop-core-harness: owned fault app already exited" >&2
    return 0
  fi
  if [[ "$status" -ne 0 || ! "$pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "desktop-core-harness: refusing unproven fault app cleanup" >&2
    return 1
  fi
  # Signal exactly the pid whose bundle path, process-start identity, command
  # hash, and unguessable launch token were just revalidated. Never quit by
  # bundle id/name and never scan-kill a matching process.
  kill -TERM "$pid" 2>/dev/null || return 1
  for attempt in $(seq 1 50); do
    set +e
    validated_fault_app_pid >/dev/null
    status=$?
    set -e
    [[ "$status" -eq 3 ]] && return 0
    [[ "$status" -eq 0 ]] || {
      echo "desktop-core-harness: fault app ownership changed during cleanup" >&2
      return 1
    }
    sleep 0.1
  done
  echo "desktop-core-harness: owned fault app did not stop; preserving evidence" >&2
  return 1
}

harness_auth_host() {
  python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "scripts" / "dev-harness"))
from dev_harness import config

print(config.load_config(repo_root).auth_host)
PY
}

stop_fault_stack() {
  local status=0
  if [[ -n "$FAULT_FLOW_PID" ]]; then
    kill -TERM "$FAULT_FLOW_PID" 2>/dev/null || true
    wait "$FAULT_FLOW_PID" 2>/dev/null || true
    FAULT_FLOW_PID=""
  fi
  if [[ "$FAULT_RUN_STARTED" -eq 1 ]]; then
    if [[ -n "$FAULT_RUN_PID" ]]; then
      kill "$FAULT_RUN_PID" 2>/dev/null || true
      wait "$FAULT_RUN_PID" 2>/dev/null || true
      FAULT_RUN_PID=""
    fi
    FAULT_RUN_STARTED=0
  fi
  if [[ -x "$SCRIPT_DIR/omi-fault-inject.sh" ]]; then
    OMI_FAULT_STATE_DIR="$FAULT_STATE_DIR" "$SCRIPT_DIR/omi-fault-inject.sh" stop >/dev/null 2>&1 || status=1
  fi
  return "$status"
}

write_fault_cleanup_evidence() {
  local status="$1" detail="$2"
  [[ -n "$FAULT_RUN_DIR" ]] || return 0
  python3 - "$FAULT_RUN_DIR/fault-cleanup.json" "$status" "$detail" "$FAULT_APP_RECORD" <<'PY'
import json
import sys
from pathlib import Path
path, status, detail, record = sys.argv[1:]
Path(path).write_text(json.dumps({
    "cleanup_status": status,
    "detail": detail,
    "fault_app_record": record or None,
}, sort_keys=True) + "\n", encoding="utf-8")
PY
}

cleanup_fault_suite() {
  local status=0 detail="stopped"
  [[ "$FAULT_CLEANUP_DONE" -eq 0 ]] || return "$FAULT_CLEANUP_STATUS"
  FAULT_CLEANUP_DONE=1
  if [[ "$FAULT_APP_LAUNCH_REQUESTED" -eq 1 ]]; then
    if [[ -z "$FAULT_APP_RECORD" || ! -f "$FAULT_APP_RECORD" ]]; then
      echo "desktop-core-harness: fault app launch proof is missing; preserving run evidence" >&2
      status=1
      detail="missing-launch-proof"
    elif ! stop_recorded_fault_app; then
      status=1
      detail="unproven-or-unreclaimed-app"
    fi
  fi
  # App cleanup comes first: run.sh may have detached from open, so killing its
  # shell cannot prove that the app exited. The isolated fault server is stopped
  # only after the app decision and evidence are recorded.
  if ! stop_fault_stack; then
    status=1
    [[ "$detail" == stopped ]] && detail="fault-server-cleanup-failed"
  fi
  if [[ "$status" -eq 0 ]]; then
    write_fault_cleanup_evidence stopped "$detail"
  else
    write_fault_cleanup_evidence failed "$detail"
  fi
  FAULT_CLEANUP_STATUS="$status"
  return "$status"
}

fault_suite_exit_trap() {
  local original_status=$?
  trap - EXIT
  if ! cleanup_fault_suite; then
    [[ "$original_status" -ne 0 ]] || exit 1
  fi
  exit "$original_status"
}

start_fault_stack() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "desktop-core-harness: --fault-suite requires macOS" >&2
    exit 1
  fi
  refuse_prod_bundle "$FAULT_BUNDLE"
  OMI_FAULT_STATE_DIR="$FAULT_STATE_DIR" "$SCRIPT_DIR/omi-fault-inject.sh" stop >/dev/null 2>&1 || true
  eval "$(OMI_FAULT_STATE_DIR="$FAULT_STATE_DIR" OMI_FAULT_OWNERSHIP_TOKEN="$FAULT_RUN_TOKEN" "$SCRIPT_DIR/omi-fault-inject.sh" start error --port "$FAULT_PORT")"
  echo "desktop-core-harness: fault inject at $OMI_FAULT_URL"
  local auth_host
  auth_host="$(harness_auth_host)"
  auth_host="${auth_host:-127.0.0.1:9099}"
  # Auth seed runs inside ./run.sh after install (passes APP_PATH for Keychain ACL).
  # Do not pre-seed here — without the installed .app path, seed refuses to write tokens.
  (
    cd "$DESKTOP_DIR"
    OMI_DESKTOP_LOCAL_PROFILE=1 \
      OMI_HARNESS_INSTANCE="${OMI_HARNESS_INSTANCE:-${OMI_LOCAL_INSTANCE:-fault-suite}}" \
      OMI_HARNESS_OWNERSHIP_TOKEN="${OMI_HARNESS_OWNERSHIP_TOKEN:-${OMI_FAULT_OWNERSHIP_TOKEN:-}}" \
      OMI_SKIP_AUTH_SEED=1 \
      OMI_SKIP_SETTINGS_SEED=1 \
      OMI_LOCAL_PROFILE_STORAGE_NAME="$FAULT_BUNDLE" \
      OMI_LOCAL_AUTH_USER=alice \
      OMI_LOCAL_AUTH_EMAIL=alice@local.omi.invalid \
      OMI_LOCAL_AUTH_PASSWORD=alice-local-password-030 \
      OMI_LOCAL_AUTH_DISPLAY_NAME='Synthetic Alice' \
      FIREBASE_AUTH_EMULATOR_HOST="$auth_host" \
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
      OMI_DESKTOP_LAUNCH_SIGNAL_FILE="$FAULT_LAUNCH_SIGNAL_FILE" \
      OMI_DESKTOP_LAUNCH_TOKEN="$FAULT_LAUNCH_TOKEN" \
      ./run.sh
  ) &
  FAULT_RUN_PID=$!
  FAULT_RUN_STARTED=1
  FAULT_APP_LAUNCH_REQUESTED=1
  local expected_bundle="com.omi.${FAULT_BUNDLE}"
  # A cold qualification cache can spend several minutes creating the named
  # fault bundle before the bridge exists. Do not turn that bounded build time
  # into a false fault-suite failure; an explicit override keeps local probes
  # fast while the qualification default covers a clean SwiftPM build.
  local bridge_ready_attempts="${OMI_FAULT_BRIDGE_READY_ATTEMPTS:-210}"
  [[ "$bridge_ready_attempts" =~ ^[1-9][0-9]*$ ]] || {
    echo "desktop-core-harness: OMI_FAULT_BRIDGE_READY_ATTEMPTS must be a positive integer" >&2
    return 1
  }
  local attempt
  for attempt in $(seq 1 "$bridge_ready_attempts"); do
    if verify_fault_bundle_health "$PORT" "$expected_bundle" 2>/dev/null; then
      OMI_AUTOMATION_PORT="$PORT" "$SCRIPT_DIR/omi-ctl" wait-ready 90
      # The detached `open` launcher can make the bridge healthy before its
      # owner-only launch signal is written. Wait for that proof before
      # recording the process, otherwise a fast runner can report a false
      # missing-launch-proof failure.
      wait_for_fault_launch_signal
      record_owned_fault_app
      echo "desktop-core-harness: $FAULT_BUNDLE bridge ready on port $PORT (bundle: $expected_bundle)"
      return 0
    fi
    # `open` returns after dispatching the app. Once the signed owner-only
    # launch signal exists, run.sh is allowed to exit while its app remains
    # detached; the token-bound process record below is the lifecycle owner.
    if ! kill -0 "$FAULT_RUN_PID" 2>/dev/null && [[ ! -f "$FAULT_LAUNCH_SIGNAL_FILE" ]]; then
      echo "desktop-core-harness: $FAULT_BUNDLE launch exited before bridge was ready" >&2
      return 1
    fi
    sleep 2
  done
  echo "desktop-core-harness: timed out waiting for $FAULT_BUNDLE bridge on port $PORT" >&2
  return 1
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

run_fault_flow_file() {
  local flow_path="$1" run_dir="$2" worker_status=0 flow_passed
  FAULT_FLOW_RESULT_FILE="$run_dir/fault-flow-result"
  (
    run_flow_file "$flow_path" "$run_dir"
    printf '%s\n%s\n' "$PASSED" "$FLOW_RESULTS" > "$FAULT_FLOW_RESULT_FILE"
  ) &
  FAULT_FLOW_PID=$!
  set +e
  wait "$FAULT_FLOW_PID"
  worker_status=$?
  set -e
  FAULT_FLOW_PID=""
  if [[ "$worker_status" -ne 0 || ! -f "$FAULT_FLOW_RESULT_FILE" ]]; then
    PASSED=false
    return 1
  fi
  flow_passed="$(sed -n '1p' "$FAULT_FLOW_RESULT_FILE")"
  FLOW_RESULTS="$(sed -n '2p' "$FAULT_FLOW_RESULT_FILE")"
  [[ "$flow_passed" == true ]] || PASSED=false
}

if [[ "$SELF_CHECK" -eq 1 ]]; then
  run_self_check
  exit 0
fi

if [[ "$FAULT_SUITE" -eq 1 ]]; then
  RUN_DIR="$HARNESS_ROOT/$(run_id)-fault"
  mkdir -p "$RUN_DIR"
  chmod 700 "$RUN_DIR"
  FAULT_RUN_DIR="$RUN_DIR"
  # Qualification binds this state to its sentinel-protected lease root. Honor
  # that handoff so authenticated lease release can reclaim the exact tokened
  # listener if this harness is interrupted before its normal stop path.
  FAULT_STATE_DIR="${OMI_FAULT_STATE_DIR:-$RUN_DIR/fault-inject}"
  mkdir -p "$FAULT_STATE_DIR"
  chmod 700 "$FAULT_STATE_DIR"
  FAULT_RUN_TOKEN="$(fault_token_for_run)"
  FAULT_LAUNCH_TOKEN="$FAULT_RUN_TOKEN"
  FAULT_BUNDLE="$(fault_bundle_for_run "$FAULT_RUN_TOKEN")"
  FAULT_LAUNCH_SIGNAL_FILE="$RUN_DIR/fault-launch.signal"
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  START_SEC=$(date +%s)
  FLOW_RESULTS="[]"
  PASSED=true
  trap fault_suite_exit_trap EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  if ! start_fault_stack; then
    PASSED=false
  else
    run_fault_flow_file "$DESKTOP_DIR/e2e/flows/chat-fault-5xx.yaml" "$RUN_DIR"
  fi
  if ! cleanup_fault_suite; then
    PASSED=false
  fi
  trap - EXIT INT TERM HUP
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
  # If a named bundle is already listening on --port, also verify /health
  # identity + agent protocol readiness; offline-only unit checks leave the port
  # closed and skip that probe.
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "desktop-core-harness: --readiness requires macOS (trusted self-hosted M1)" >&2
    exit 1
  fi
  RUN_DIR="$HARNESS_ROOT/$(run_id)-readiness"
  mkdir -p "$RUN_DIR"
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  START_SEC=$(date +%s)
  FLOW_RESULTS="[]"
  trap maybe_teardown_dev_stack EXIT
  run_self_check
  ensure_dev_stack
  maybe_verify_readiness_bundle_health
  maybe_teardown_dev_stack
  trap - EXIT
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
