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
import argparse
import json
import os
import tempfile
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

trace_context = module.HarnessContext(
    base_url="http://127.0.0.1:59999",
    flow_path=Path("flow.yaml"),
    run_dir=Path("runs"),
    steps_dir=Path("runs/steps"),
    lane="bridge",
    log_path=Path("/private/tmp/omi/harness-test.log"),
    log_start=0,
    bundle_id=None,
    process_match=None,
)
original_recent_traces = module.recent_traces
module.recent_traces = lambda _ctx: [
    {"path": "/navigate", "durationMs": 12},
    {"path": "/navigate", "durationMs": 145},
    {"path": "/state", "durationMs": 4},
]
with tempfile.TemporaryDirectory() as directory:
    trace_artifact = Path(directory) / "traces.json"
    ok, error = module.assert_trace(
        trace_context, {"latest": True, "trace.path": "/navigate", "trace.durationMs": {"max": 100}}, trace_artifact
    )
    assert not ok and "145" in error, error
    ok, error = module.assert_trace(
        trace_context, {"trace.path": "/navigate", "trace.durationMs": {"max": 100}}, trace_artifact
    )
    assert ok, error
module.recent_traces = lambda _ctx: [
    {"path": "/navigate", "durationMs": 12},
    {"path": "/state", "durationMs": 4},
]
with tempfile.TemporaryDirectory() as directory:
    trace_artifact = Path(directory) / "traces.json"
    ok, error = module.assert_trace(
        trace_context, {"latest": True, "trace.path": "/navigate", "trace.durationMs": {"max": 100}}, trace_artifact
    )
    assert ok, error
module.recent_traces = lambda _ctx: [
    {"path": "/navigate", "method": "POST", "statusCode": 200, "durationMs": 12},
    {"path": "/navigate", "method": "POST", "statusCode": 500, "durationMs": 8},
    {"path": "/state", "method": "GET", "statusCode": 200, "durationMs": 4},
]
with tempfile.TemporaryDirectory() as directory:
    trace_artifact = Path(directory) / "traces.json"
    # The latest /navigate returned 500. The selector must NOT filter it out,
    # so statusCode: 200 must fail on the newest matching route trace.
    ok, error = module.assert_trace(
        trace_context,
        {"latest": True, "trace.path": "/navigate", "trace.method": "POST", "trace.statusCode": 200, "trace.durationMs": {"max": 100}},
        trace_artifact,
    )
    assert not ok, "latest failed trace must not be hidden by an earlier success"
    # Duration alone should also fail because the latest trace is the 500 (8ms),
    # not the earlier 200 (12ms) — the selector must pick the newest by identity.
    ok, error = module.assert_trace(
        trace_context,
        {"latest": True, "trace.path": "/navigate", "trace.method": "POST", "trace.durationMs": {"max": 100}},
        trace_artifact,
    )
    assert ok, error

module.recent_traces = original_recent_traces

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
assert "timeout_seconds: 30" in s1_block, "rewind freshness wait must remain bounded"
assert "stability_window_seconds:" in s1_block, "rewind freshness must remain stable before action dispatch"
assert "halt_on_failure: true" in s1_block, "failed rewind readiness must halt before the action"

module.state_snapshot = lambda _ctx: {"selectedSettingsSection": "Rewind", "snapshotStale": True}
stale_ok, stale_state = module.wait_for_state(wait_context, wait_expectations, timeout=0.001)
module.state_snapshot = original_state_snapshot
assert not stale_ok and stale_state["snapshotStale"] is True, "persistent MainActor contention must still fail closed"


def run_rewind_flow_case(state_sequence, action_response):
    flow = {
        "version": 2,
        "name": "rewind-settings-gating-contract",
        "steps": [
            {
                "id": "S1",
                "name": "readiness",
                "bridge.navigate": {"target": "settings", "settingsSection": "Rewind"},
                "wait": wait_expectations,
                "timeout_seconds": 0.12,
                "stability_window_seconds": 0.04,
                "halt_on_failure": True,
            },
            {
                "id": "S2",
                "name": "snapshot action",
                "bridge.action": {"name": "rewind_settings_snapshot"},
                "expect": {"ok": True},
            },
        ],
    }
    originals = {
        name: getattr(module, name)
        for name in (
            "read_yaml",
            "validate_flow_schema",
            "create_context",
            "request_json",
            "collect_logs",
            "recent_traces",
        )
    }
    original_monotonic = module.time.monotonic
    original_sleep = module.time.sleep
    clock = [0.0]
    navigation_started = [False]
    state_calls = []
    action_calls = []

    def fake_request_json(_base_url, method, route, body=None, authenticate=True):
        del body, authenticate
        if method == "POST" and route == "/traces/clear":
            return {"ok": True}
        if method == "GET" and route == "/capabilities":
            return {"ok": True, "result": {}}
        if method == "GET" and route == "/state":
            if not navigation_started[0]:
                return {"ok": True, "result": {"selectedSettingsSection": "Rewind", "snapshotStale": False}}
            state_calls.append(len(state_calls))
            state = state_sequence[min(len(state_calls) - 1, len(state_sequence) - 1)]
            return {"ok": True, "result": state}
        if method == "POST" and route == "/navigate":
            navigation_started[0] = True
            return {"ok": True}
        if method == "POST" and route == "/action":
            action_calls.append({"state_call_count": len(state_calls), "response": action_response})
            return action_response
        if method == "GET" and route == "/traces/recent":
            return {"ok": True, "result": []}
        raise AssertionError((method, route))

    def fake_sleep(seconds):
        clock[0] += seconds

    def fake_create_context(args, case_flow_path, run_dir, lane):
        return module.HarnessContext(
            base_url=f"http://127.0.0.1:{args.port}",
            flow_path=case_flow_path,
            run_dir=run_dir,
            steps_dir=run_dir / "steps",
            lane=lane,
            log_path=Path("/private/tmp/omi/harness-test.log"),
            log_start=0,
            bundle_id=None,
            process_match=None,
        )

    try:
        module.read_yaml = lambda _path: flow
        module.validate_flow_schema = lambda _flow, _args: 2
        module.create_context = fake_create_context
        module.request_json = fake_request_json
        module.collect_logs = lambda _ctx: {"error_count": 0}
        module.recent_traces = lambda _ctx: []
        module.time.monotonic = lambda: clock[0]
        module.time.sleep = fake_sleep
        with tempfile.TemporaryDirectory() as out:
            args = argparse.Namespace(
                flow=str(flow_path),
                out=out,
                lane="bridge",
                port=59999,
                bundle_id=None,
                process_match=None,
            )
            code, _run_dir, metrics = module.run_flow_once(args)
    finally:
        for name, value in originals.items():
            setattr(module, name, value)
        module.time.monotonic = original_monotonic
        module.time.sleep = original_sleep
    return code, metrics, state_calls, action_calls


fresh_stale_fresh = [
    {"selectedSettingsSection": "Rewind", "snapshotStale": False},
    {"selectedSettingsSection": "Rewind", "snapshotStale": True},
    {"selectedSettingsSection": "Rewind", "snapshotStale": False},
]
stable_code, stable_metrics, stable_state_calls, stable_action_calls = run_rewind_flow_case(
    fresh_stale_fresh, {"ok": True, "result": {"accepted": True}}
)
assert stable_code == 0, stable_metrics
assert len(stable_action_calls) == 1, "fresh-stale-fresh readiness must dispatch exactly once"
assert stable_action_calls[0]["state_call_count"] >= 5, (
    "action must wait for a fresh snapshot to remain stable across the configured window",
    stable_state_calls,
    stable_action_calls,
)

stale_code, stale_metrics, _, stale_action_calls = run_rewind_flow_case(
    [{"selectedSettingsSection": "Rewind", "snapshotStale": True}],
    {"ok": True, "result": {"accepted": True}},
)
assert stale_code == 1, stale_metrics
assert not stale_action_calls, "permanently stale readiness must dispatch zero actions"
assert [step["id"] for step in stale_metrics["steps"]] == ["S1"]

timeout_code, timeout_metrics, _, timeout_action_calls = run_rewind_flow_case(
    [{"selectedSettingsSection": "Rewind", "snapshotStale": False}],
    {"ok": False, "error": "connection_timeout: timed out"},
)
assert timeout_code == 1, timeout_metrics
assert len(timeout_action_calls) == 1, "action timeout must remain terminal and single-attempt"
assert [step["id"] for step in timeout_metrics["steps"]] == ["S1", "S2"]


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

from pathlib import Path
import tempfile

snapshot = {
    "elements": [
        {"identifier": "chat-first-sidebar-chat", "label": "Chat"},
        {"identifier": "chat-first-sidebar-goals", "title": "Goals"},
        {"identifier": "chat-first-sidebar-tasks", "attrs": {"AXLabel": "Tasks"}},
    ]
}
snapshot_json = module.json.dumps(snapshot)
commands = []
def fake_agent_swift(_ctx, args):
    commands.append(args)
    stdout = snapshot_json if args[:2] == ["snapshot", "-i"] else "activated"
    return module.subprocess.CompletedProcess(args, 0, stdout)

real_agent_swift = module.run_agent_swift
module.run_agent_swift = fake_agent_swift
with tempfile.TemporaryDirectory() as directory:
    artifacts = Path(directory)
    ctx = module.HarnessContext(
        base_url="http://127.0.0.1:9",
        flow_path=Path("flow.yaml"),
        run_dir=artifacts,
        steps_dir=artifacts,
        lane="ui",
        log_path=artifacts / "missing.log",
        log_start=0,
        bundle_id="com.omi.omi-chat-first-e2e",
        process_match=None,
    )
    ok, error = module.assert_ax(
        ctx,
        {
            "identifiers_visible": ["chat-first-sidebar-chat", "chat-first-sidebar-goals"],
            "focus_order": [
                "chat-first-sidebar-chat",
                "chat-first-sidebar-goals",
                "chat-first-sidebar-tasks",
            ],
            "voiceover_labels": {
                "chat-first-sidebar-chat": "Chat",
                "chat-first-sidebar-goals": "Goals",
                "chat-first-sidebar-tasks": "Tasks",
            },
        },
        artifacts / "ax.json",
    )
    assert ok, error
    ok, error = module.activate_ax(ctx, {"identifier": "chat-first-sidebar-goals"}, artifacts / "activate.json")
    assert ok, error
    assert commands[-1] == ["find", "identifier", "chat-first-sidebar-goals", "click"]
    ok, error = module.activate_ax(ctx, {"identifier": "not a stable id"}, artifacts / "activate-invalid.json")
    assert not ok and "stable identifier" in error
    ok, error = module.assert_ax(
        ctx,
        {"focus_order": ["chat-first-sidebar-goals", "chat-first-sidebar-chat"]},
        artifacts / "ax-reordered.json",
    )
    assert not ok and "keyboard focus order" in error
    ok, error = module.assert_ax(
        ctx,
        {"voiceover_labels": {"chat-first-sidebar-goals": "unexpected label"}},
        artifacts / "ax-label-mismatch.json",
    )
    assert not ok and "chat-first-sidebar-goals" in error
    assert "unexpected label" not in error and "Goals" not in error

    production_ctx = module.HarnessContext(
        base_url=ctx.base_url,
        flow_path=ctx.flow_path,
        run_dir=ctx.run_dir,
        steps_dir=ctx.steps_dir,
        lane=ctx.lane,
        log_path=ctx.log_path,
        log_start=ctx.log_start,
        bundle_id="com.omi.computer-macos",
        process_match=None,
    )
    module.run_agent_swift = real_agent_swift
    try:
        module.run_agent_swift(production_ctx, ["snapshot", "-i", "--json"])
    except RuntimeError as exc:
        assert "named non-production" in str(exc)
    else:
        raise AssertionError("production bundle was not rejected")

assert module.NAMED_NON_PRODUCTION_BUNDLE_PREFIX == "com.omi.omi-"

# Missing token must fail loud (not silently omit Authorization).
del os.environ["OMI_AUTOMATION_TOKEN"]
os.environ["TMPDIR"] = "/tmp"
os.environ.pop("OMI_AUTOMATION_TOKEN_FILE", None)
missing = module.request_json("http://127.0.0.1:59999", "GET", "/state")
assert missing.get("ok") is False
assert "automation_token_missing" in str(missing.get("error", ""))
PY

python3 - "$MACOS_DIR/scripts/desktop-flow-lint.py" <<'PY'
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

path = sys.argv[1]
sys.path.insert(0, str(Path(path).parent))
loader = importlib.machinery.SourceFileLoader("desktop_flow_lint", path)
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)

assert "ax.activate" in module.TYPED_STEP_KEYS
assert "chat_first_runtime_snapshot" in module.registered_actions()
assert module.lint_ax_step(
    Path("chat-first.yaml"),
    {
        "ax.activate": {"identifier": "chat-first-sidebar-goals"},
        "ax.expect": {
            "focus_order": ["chat-first-sidebar-chat", "chat-first-sidebar-goals"],
            "voiceover_labels": {"chat-first-sidebar-chat": "Chat"},
        },
    },
) == []
errors = module.lint_ax_step(Path("chat-first.yaml"), {"ax.activate": {"identifier": "not a stable id"}})
assert errors and "stable identifier" in errors[0]
errors = module.lint_ax_step(
    Path("chat-first.yaml"),
    {"ax.expect": {"focus_order": ["chat-first-sidebar-chat", "chat-first-sidebar-chat"]}},
)
assert errors and "must not repeat" in errors[0]
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
