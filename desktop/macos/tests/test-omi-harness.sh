#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS="$MACOS_DIR/scripts/omi-harness"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

cat >"$TMPDIR/yaml.py" <<'PY'
def safe_load(handle):
    data = {}
    for raw_line in handle.read().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value == "[]":
            parsed = []
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value
        data[key.strip()] = parsed
    return data
PY
export PYTHONPATH="$TMPDIR${PYTHONPATH:+:$PYTHONPATH}"

python3 - "$HARNESS" <<'PY'
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

path = sys.argv[1]
loader = importlib.machinery.SourceFileLoader("omi_harness", path)
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)

assert module.expectation_matches({"result": {"count": "1"}}, {"result.count": {"min": 1}})
assert module.expectation_matches({"result": {"count": 2}}, {"result.count": {"min": "1", "max": "2"}})
assert not module.expectation_matches({"result": {"count": "0"}}, {"result.count": {"min": 1}})
assert not module.expectation_matches({"result": {"count": "one"}}, {"result.count": {"min": 1}})
assert not module.expectation_matches({"result": {"count": "1"}}, {"result.count": {"minimum": 1}})
assert module.expectation_matches({"result": {"value": "1"}}, {"result.value": "1"})
assert not module.expectation_matches({"result": {"value": "1"}}, {"result.value": 1})
assert module.expectation_matches({"result": {"value": {"min": 1}}}, {"result.value": {"min": 1}})
assert module.expectation_matches({"result": {"id": "memory-1"}}, {"result.id": {"exists": True}})
assert not module.expectation_matches({"result": {}}, {"result.id": {"exists": True}})
assert module.expectation_matches({"result": {}}, {"result.id": {"exists": False}})
assert not module.expectation_matches({"result": {"id": "memory-1"}}, {"result.id": {"exists": "yes"}})
assert not module.expectation_matches({"result": {"id": 1}}, {"result.id": {"exists": True, "min": 1}})
assert module.expectation_matches(
    {"result": {"error_message": "backend request failed with HTTP 500"}},
    {"result.error_message": {"contains": "HTTP 500"}},
)
assert not module.expectation_matches(
    {"result": {"error_message": "bridge unavailable"}},
    {"result.error_message": {"contains": "HTTP 500"}},
)

mismatch = module.expectation_mismatches(
    {"result": {"count": "1"}}, {"result.count": {"minimum": 1}}
)["result.count"]
assert "unsupported expectation operator" in mismatch["reason"]

assert module.log_path_from_health(
    {"ok": True, "logFilePath": "/private/tmp/omi/com.omi.qa/pid-1.log"}
).as_posix().endswith("pid-1.log")
assert module.log_path_from_health({"ok": True}, "/tmp/explicit.log").as_posix() == "/tmp/explicit.log"
try:
    module.log_path_from_health({"ok": True, "logFilePath": "relative.log"})
except RuntimeError:
    pass
else:
    raise AssertionError("relative health log path must fail loudly")

flow_path = Path(path).parent.parent / "e2e/flows/rewind-settings.yaml"
flow_text = flow_path.read_text(encoding="utf-8")
s1_block = flow_text.split("  - id: S1", 1)[1].split("  - id: S2", 1)[0]
wait_expectations = {"state.selectedSettingsSection": "Rewind"}
freshness_match = re.search(r"state\.snapshotStale:\s*(true|false)", s1_block)
if freshness_match:
    wait_expectations["state.snapshotStale"] = freshness_match.group(1) == "true"

state_sequence = [
    {"selectedSettingsSection": "Rewind", "snapshotStale": True},
    {"selectedSettingsSection": "Rewind", "snapshotStale": False},
]
state_calls = []
original_state_snapshot = module.state_snapshot
wait_context = module.HarnessContext(
    base_url="http://127.0.0.1:59999",
    flow_path=flow_path,
    run_dir=Path("runs"),
    steps_dir=Path("runs/steps"),
    lane="bridge",
    log_path=Path("/private/tmp/omi/harness-test.log"),
    log_start=0,
    bundle_id=None,
    process_match=None,
)
module.state_snapshot = lambda _ctx: state_calls.append(len(state_calls)) or state_sequence[min(len(state_calls) - 1, 1)]
wait_ok, wait_state = module.wait_for_state(wait_context, wait_expectations, timeout=1.0)
module.state_snapshot = original_state_snapshot
assert wait_ok and wait_state["snapshotStale"] is False, (wait_ok, wait_state, wait_expectations, state_calls)
assert len(state_calls) == 2, "rewind flow must not start its MainActor action from a stale cached state"
assert "timeout_seconds: 30" in s1_block, "rewind freshness wait must remain bounded"

module.state_snapshot = lambda _ctx: {"selectedSettingsSection": "Rewind", "snapshotStale": True}
stale_ok, stale_state = module.wait_for_state(wait_context, wait_expectations, timeout=0.001)
module.state_snapshot = original_state_snapshot
assert not stale_ok and stale_state["snapshotStale"] is True, "persistent MainActor contention must still fail closed"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


requests = []


def fake_urlopen(request, timeout):
    route = request.full_url.rsplit(":59999", 1)[1]
    requests.append(
        {
            "route": route,
            "method": request.get_method(),
            "authorization": request.get_header("Authorization"),
        }
    )
    if route == "/health":
        return FakeResponse({"ok": True, "logFilePath": "/private/tmp/omi/harness-test.log"})
    if route == "/state":
        return FakeResponse({"ok": True, "result": {"selectedTab": "home"}})
    if route == "/action":
        return FakeResponse({"ok": True, "result": {"accepted": True}})
    raise AssertionError(f"unexpected route: {route}")


os.environ["OMI_AUTOMATION_TOKEN"] = "test-automation-token"
module.urllib.request.urlopen = fake_urlopen
assert module.resolve_log_path("http://127.0.0.1:59999").as_posix().endswith("harness-test.log")
assert module.state_snapshot(
    module.HarnessContext(
        base_url="http://127.0.0.1:59999",
        flow_path=module.Path("flow.yaml"),
        run_dir=module.Path("runs"),
        steps_dir=module.Path("runs/steps"),
        lane="bridge",
        log_path=module.Path("/private/tmp/omi/harness-test.log"),
        log_start=0,
        bundle_id=None,
        process_match=None,
    )
) == {"selectedTab": "home"}
assert module.request_json(
    "http://127.0.0.1:59999", "POST", "/action", {"name": "refresh_all_data"}
)["result"]["accepted"]

assert [(request["method"], request["route"]) for request in requests] == [
    ("GET", "/health"),
    ("GET", "/state"),
    ("POST", "/action"),
]
assert requests[0]["authorization"] is None
assert requests[1]["authorization"] == "Bearer test-automation-token"
assert requests[2]["authorization"] == "Bearer test-automation-token"
PY

write_flow() {
  local path="$1" version="$2"
  cat >"$path" <<YAML
version: $version
name: schema-$version
steps: []
YAML
}

write_flow "$TMPDIR/future.yaml" 3
if "$HARNESS" run "$TMPDIR/future.yaml" --out "$TMPDIR/runs" >"$TMPDIR/future.out" 2>"$TMPDIR/future.err"; then
  fail "future schema unexpectedly succeeded"
fi
if ! grep -q "newer than supported version 2" "$TMPDIR/future.err"; then
  fail "future schema error did not mention supported version"
fi

write_flow "$TMPDIR/legacy.yaml" 1
if "$HARNESS" run "$TMPDIR/legacy.yaml" --out "$TMPDIR/runs" >"$TMPDIR/legacy.out" 2>"$TMPDIR/legacy.err"; then
  fail "legacy schema unexpectedly succeeded without explicit compatibility"
fi
if ! grep -q "requires explicit compatibility" "$TMPDIR/legacy.err"; then
  fail "legacy schema error did not mention explicit compatibility"
fi

if "$HARNESS" run "$TMPDIR/legacy.yaml" --allow-legacy-flow-version --out "$TMPDIR/runs" \
    --port 9 >"$TMPDIR/legacy-opt-in.out" 2>"$TMPDIR/legacy-opt-in.err"; then
  fail "legacy opt-in unexpectedly passed against closed bridge port"
fi
if grep -q "requires explicit compatibility" "$TMPDIR/legacy-opt-in.err"; then
  fail "legacy opt-in was still rejected by schema compatibility gate"
fi

echo "omi-harness schema tests passed"
