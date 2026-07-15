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
PY

python3 - "$MACOS_DIR/scripts/desktop-flow-lint.py" <<'PY'
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

path = sys.argv[1]
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
