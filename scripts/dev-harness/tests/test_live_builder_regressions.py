"""Builder regressions for lazy V1 holes and real-process ownership.

Spine contracts already close these cases. These tests keep a cheap copy of the
wrong implementation's failure mode in the ordinary harness suite, including two
behaviors that must use a real child process rather than a mock.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev_harness import live_session as live
from spine.test_live_session import rig  # noqa: F401  # fixture


def test_unready_start_must_spawn_and_probe_controls(rig):
    # Lazy hole 1: returning blocked without a child or wait_ready RPC.
    rig.mode = "unready"
    engine = rig.engine()
    assert engine.start()["outcome"] == "blocked"
    assert len(rig.children) == 1
    assert rig.children[0].process.pid > 0
    names = [c["params"].get("methodName") for c in rig.calls() if c["method"] == "app.callServiceExtension"]
    assert "ext.omi.controls.capabilities" in names
    assert "ext.omi.controls.wait_ready" in names


def test_controls_fault_must_send_the_rpc_before_rejecting(rig):
    # Lazy hole 2: any non-ok without sending ext.omi.controls.fault.
    engine = rig.engine()
    engine.start()
    failed = engine.request("controls", generation=1, params={"method": "fault", "params": {"fault": "unknown"}})
    assert failed["outcome"] == "rejected"
    assert failed["outcome"] != "ok"
    assert rig.calls()[-1]["params"] == {
        "appId": "app-fixture",
        "methodName": "ext.omi.controls.fault",
        "params": {"fault": "unknown"},
    }


def test_failed_reload_error_codes_are_distinct(rig):
    # Lazy hole 4: treat-any-slow-child-as-blocked without distinguishing modes.
    mapping = {
        "reject": ("rejected", "reload-rejected"),
        "missing-code": ("blocked", "malformed-response"),
        "die": ("blocked", "daemon-exited"),
        "wedge": ("blocked", "deadline"),
    }
    for mode, (outcome, error_code) in mapping.items():
        rig.mode = mode
        engine = rig.engine()
        engine.start()
        reply = engine.request("reload", generation=1, timeout_s=0.2)
        assert reply["outcome"] == outcome, mode
        assert reply["error_code"] == error_code, mode
        engine.close()


def test_verify_contacts_broker_then_refuses_missing_adapter(rig, monkeypatch):
    # Lazy hole 5: admit_attachment-only, never contacting the broker.
    from dev_harness import mobile_verify

    engine = rig.engine()
    engine.start()
    calls = []

    def dispatch(root, session_id, operation, params=None):
        calls.append((session_id, operation))
        assert operation == "status"
        return engine.request("status", generation=1)

    monkeypatch.setattr(live, "dispatch", dispatch)
    assert mobile_verify.main(["fast", "--session", "oms-fixture", "--all"]) == 2
    assert calls == [("oms-fixture", "status")]


def test_second_session_keeps_running_after_peer_close(rig):
    # Lazy hole 6: distinct cwd is not enough; close-one must keep the other.
    import copy
    from dev_harness import session_evidence as se

    first = rig.engine()
    assert first.start()["outcome"] == "ok"
    second_root = rig.directory.parent / "second-checkout"
    (second_root / "app").mkdir(parents=True)
    (second_root / "app" / ".dev.env").write_text("API_BASE_URL=\n")
    second_dir = second_root / "oms-second"
    second_dir.mkdir()
    (second_dir / "seed.json").write_bytes((rig.directory / "seed.json").read_bytes())
    lease = copy.deepcopy(rig.lease)
    lease.update({"session_id": "oms-second", "harness_instance": "second"})
    lease["device"]["udid"] = "second-device"
    evidence = copy.deepcopy(rig.evidence)
    evidence["session_id"] = "oms-second"
    (second_dir / "fixture.apk").write_bytes(rig.artifact.read_bytes())
    se.write_evidence(second_dir / "evidence.json", evidence)
    second = live.LiveSession(
        second_root,
        second_dir,
        load_lease=lambda: lease,
        source=lambda: rig.stamp,
        factory=rig.factory,
        screenshot=rig.screenshot,
    )
    assert second.start()["outcome"] == "ok"
    first.close()
    assert rig.children[1].process.poll() is None
    assert second.request("reload", generation=1)["outcome"] == "ok"


def test_flutter_child_death_mid_reload_is_blocked_never_success(rig):
    # Real child process (fake_flutter.py); death is sys.exit, not a mock receive.
    rig.mode = "die"
    engine = rig.engine()
    engine.start()
    child = rig.children[0].process
    assert child.poll() is None
    reply = engine.request("reload", generation=1, timeout_s=1)
    assert reply["outcome"] == "blocked"
    assert reply["outcome"] != "ok"
    assert reply["error_code"] == "daemon-exited"
    assert child.poll() is not None


def test_teardown_never_signals_a_live_pid_with_mismatched_identity(tmp_path):
    # Real OS PID is alive; start time / marker / boot id do not match.
    from dev_harness import mobile_session as ms

    root = Path(__file__).resolve().parents[3]
    env = {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}
    lease = ms.acquire(root, env, name="pid-reuse", listeners=lambda p: ())
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    try:
        recorded = live.BrokerIdentity(
            lease["owner"]["host"],
            lease["owner"]["user"],
            "recorded-boot",
            child.pid,
            "recorded-start",
            "recorded-marker",
            1,
            str(root),
            lease["session_id"],
        )
        observed = replace(recorded, boot_id="live-boot", process_start="live-start", ownership_marker="live-marker")
        directory = ms.session_dir(root, lease["session_id"], env)
        (directory / "live.json").write_text(json.dumps({"broker": asdict(recorded), "child": asdict(recorded)}))
        signaled = []

        def probe(identity):
            return observed if child.poll() is None else None

        def terminate(pid):
            signaled.append(pid)
            os.kill(pid, signal.SIGTERM)

        with pytest.raises(live.LiveError):
            live.teardown(root, lease["session_id"], env, probe=probe, terminate=terminate)
        assert signaled == []
        assert child.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)
        if child.stdin:
            child.stdin.close()


def test_session_lifecycle_tears_down_live_before_services(tmp_path, monkeypatch):
    # Lazy hole 3: calling teardown() first then leaving the old device-before-services order.
    from dev_harness import cli
    from dev_harness import mobile_session as ms

    root = Path(__file__).resolve().parents[3]
    env = {"OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}
    lease = ms.acquire(root, env, name="lifecycle", listeners=lambda p: ())
    lease["device"] = {"kind": "simulator", "udid": "owned-device", "owner": "session"}
    ms._save_json_atomic(ms.session_dir(root, lease["session_id"], env) / "lease.json", lease)
    order = []
    monkeypatch.setattr(ms.DeviceController, "detach", lambda self, platform, device: order.append("device"))
    monkeypatch.setattr(live, "teardown", lambda *args, **kwargs: order.append("live"))
    monkeypatch.setattr(cli, "cmd_down", lambda *args: order.append("services") or 0)
    ms.stop(root, lease["session_id"], env)
    assert order == ["live", "services", "device"]


def test_cli_live_ops_refuse_real_flutter_spawn(tmp_path):
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / "scripts/dev-harness"), "OMI_LOCAL_STATE_ROOT": str(tmp_path / "state")}
    for operation in live.OPERATIONS:
        result = subprocess.run(
            [sys.executable, "-m", "dev_harness.mobile_session", "live", operation, "oms-never-acquired", "--json"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 2, (operation, result.stdout, result.stderr)
        assert result.stderr.startswith("error: "), result.stderr
        assert "Traceback" not in result.stderr
        assert "flutter run" not in result.stdout.lower()

    from dev_harness import mobile_session as ms

    lease = ms.acquire(root, env, name="cli-refuse", listeners=lambda p: ())
    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.mobile_session", "live", "reload", lease["session_id"], "--json"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "does not spawn flutter run" in result.stderr
    assert "Traceback" not in result.stderr


def _wrap_send(factory, hook):
    def create(spec):
        child = factory(spec)
        send = child.send

        def wrapped(line):
            hook(line)
            send(line)

        child.send = wrapped
        return child

    return create


def _wrap_receive(factory, hook):
    def create(spec):
        child = factory(spec)
        receive = child.receive

        def wrapped(timeout_s):
            return hook(receive, timeout_s)

        child.receive = wrapped
        return child

    return create


def test_lease_roll_during_start_readiness_does_not_publish_ok(rig):
    def hook(line):
        if "ext.omi.controls.state" in line:
            rig.lease["generation"] += 1

    rig.factory = _wrap_send(rig.factory, hook)
    engine = rig.engine()
    reply = engine.start()
    live_receipt = reply["evidence"]["live"]
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "stale-session"
    assert live_receipt["generation"] == 1
    assert live_receipt["loaded_source"] is None
    assert live_receipt["loaded_sequence"] == 0
    engine.close()


@pytest.mark.parametrize("operation", ["reload", "restart"])
def test_lease_roll_during_reload_readiness_keeps_proven_loaded_identity(rig, operation):
    armed = False

    def hook(line):
        if armed and "ext.omi.controls.state" in line:
            rig.lease["generation"] += 1

    rig.factory = _wrap_send(rig.factory, hook)
    engine = rig.engine()
    before = engine.start()["evidence"]["live"]
    armed = True
    reply = engine.request(operation, generation=1)
    live_receipt = reply["evidence"]["live"]
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "stale-session"
    assert live_receipt["generation"] == 1
    assert live_receipt["loaded_source"] == before["loaded_source"]
    assert live_receipt["loaded_sequence"] == before["loaded_sequence"]
    engine.close()


def test_lease_roll_during_controls_does_not_publish_ok(rig):
    armed = False

    def hook(line):
        if armed and "ext.omi.controls.state" in line:
            rig.lease["generation"] += 1

    rig.factory = _wrap_send(rig.factory, hook)
    engine = rig.engine()
    engine.start()
    armed = True
    reply = engine.request("controls", generation=1, params={"method": "state"})
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "stale-session"
    assert reply["evidence"]["live"]["generation"] == 1
    engine.close()


def test_lease_roll_during_screenshot_does_not_publish_ok(rig):
    engine = None

    def shot(device, path):
        rig.lease["generation"] += 1
        rig.screenshot(device, path)

    engine = live.LiveSession(
        rig.directory.parent,
        rig.directory,
        load_lease=lambda: rig.lease,
        source=lambda: rig.stamp,
        factory=rig.factory,
        screenshot=shot,
    )
    engine.start()
    reply = engine.request("screenshot", generation=1)
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "stale-session"
    assert reply["evidence"]["live"]["generation"] == 1
    engine.close()


def test_stringy_false_readiness_is_not_ready(rig):
    def hook(receive, timeout_s):
        line = receive(timeout_s)
        if not line:
            return line
        payload = json.loads(line)
        message = payload[0]
        result = message.get("result")
        if isinstance(result, dict):
            holder = result["state"] if isinstance(result.get("state"), dict) else result
            if isinstance(holder.get("readiness"), dict):
                holder["readiness"] = {"signedIn": "false", "routed": "false", "captureIdle": "false"}
                return json.dumps(payload)
        return line

    rig.factory = _wrap_receive(rig.factory, hook)
    engine = rig.engine()
    reply = engine.start()
    # Fail closed: a stringy readiness flag is malformed, not merely unready,
    # so start blocks on malformed-response instead of probing wait_ready.
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "malformed-response"
    assert reply["evidence"]["live"]["loaded_source"] is None
    engine.close()


def test_post_reload_capabilities_error_leaves_status_blocked(rig):
    armed = False
    pending_id = [None]
    base = rig.factory

    def create(spec):
        child = base(spec)
        send = child.send
        receive = child.receive

        def wrapped_send(line):
            request = json.loads(line)[0]
            send(line)
            if armed and request.get("params", {}).get("methodName") == "ext.omi.controls.capabilities":
                pending_id[0] = request["id"]

        def wrapped_receive(timeout_s):
            line = receive(timeout_s)
            if pending_id[0] is not None and line:
                message = json.loads(line)[0]
                if message.get("id") == pending_id[0]:
                    pending_id[0] = None
                    return json.dumps(
                        [{"id": message["id"], "error": {"code": -32000, "message": "capabilities failed"}}]
                    )
            return line

        child.send = wrapped_send
        child.receive = wrapped_receive
        return child

    rig.factory = create
    engine = rig.engine()
    before = engine.start()["evidence"]["live"]
    assert engine.request("status", generation=1)["result"]["state"] == "ready"
    armed = True
    reply = engine.request("reload", generation=1)
    assert reply["outcome"] == "blocked"
    assert reply["error_code"] == "malformed-response"
    assert reply["evidence"]["live"]["loaded_source"] == before["loaded_source"]
    assert reply["evidence"]["live"]["loaded_sequence"] == before["loaded_sequence"]
    assert engine.request("status", generation=1)["result"]["state"] == "blocked"
    engine.close()


def test_authorization_bearer_is_redacted_from_logs_api(rig):
    secret = "super-secret-bearer-token-99"
    armed = False

    def hook(receive, timeout_s):
        nonlocal armed
        if armed:
            armed = False
            return json.dumps(
                [
                    {
                        "event": "app.log",
                        "params": {
                            "appId": "app-fixture",
                            "log": f"Authorization: Bearer {secret}",
                            "error": False,
                        },
                    }
                ]
            )
        return receive(timeout_s)

    rig.factory = _wrap_receive(rig.factory, hook)
    engine = rig.engine()
    engine.start()
    armed = True
    engine.request("reload", generation=1)
    reply = engine.request("logs", generation=1)
    dumped = json.dumps(reply)
    assert secret not in dumped
    assert "Authorization=<redacted> " + secret not in dumped
    assert "Bearer " + secret not in dumped
    for path in rig.directory.glob("operations/*/evidence.json"):
        assert secret not in path.read_text()
    engine.close()
