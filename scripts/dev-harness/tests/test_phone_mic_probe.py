"""A hardware trace checker must reject incomplete and deliberately broken runs."""

import copy
import importlib.util
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parents[3] / "app/ios/test/phone_mic_probe/analyze.py"
spec = importlib.util.spec_from_file_location("phone_mic_probe_analyze", PROBE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BUILD = {"git_sha": "a" * 40, "inputs": {"controller.swift": "b" * 64}}


def trace():
    def event(kind, ms, frames, app_state="active", **extra):
        return {
            "kind": kind,
            "elapsed_ms": ms,
            "frames": frames,
            "bytes": frames * 320,
            "app_state": app_state,
            **extra,
        }

    events = [event("start_requested", 0, 0), event("state", 10, 0, state="running"), event("start_completed", 20, 0)]
    events += [event("sample", n * 1000, n * 10, "background" if 2 <= n <= 15 else "active") for n in range(1, 20)]
    events += [
        event("stop_requested", 20000, 200),
        event("state", 20001, 200, state="idle"),
        event("stop_completed", 20002, 200),
        event("observation_completed", 22002, 200),
    ]
    return {
        "schema": "phone-mic-device-probe/v1",
        "build": BUILD,
        "scope": "native-stream-only",
        "audio_retained": False,
        "session_id": 1,
        "events": events,
    }


def test_completed_background_capture_and_return():
    result = module.analyze(trace(), BUILD)
    assert result["checks"] == {
        "start_stop": "passed",
        "background_capture": "passed",
        "foreground_recovery": "passed",
        "interruption_recovery": "not-observed",
        "non_silent_pcm": "not-observed",
        "permission_denial": "not-observed",
        "permission_recovery": "not-observed",
        "sustained_capture": "not-observed",
    }


def test_no_background_is_not_a_background_pass():
    doc = trace()
    for event in doc["events"]:
        event["app_state"] = "active"
    assert module.analyze(doc, BUILD)["checks"]["background_capture"] == "not-observed"


def test_missing_observation_is_incomplete():
    doc = trace()
    doc["events"].pop()
    assert module.analyze(doc, BUILD)["checks"]["start_stop"] == "incomplete"


@pytest.mark.parametrize("check", ["background_capture", "foreground_recovery", "non_silent_pcm"])
@pytest.mark.parametrize("fault", ["killed", "failed_stop"])
def test_selected_capture_check_cannot_pass_without_successful_stop(check, fault, tmp_path, monkeypatch, capsys):
    import json
    import sys

    doc = trace()
    if fault == "killed":
        doc["events"] = doc["events"][:-4]
    else:
        doc["events"][-3]["state"] = "running"
    doc["events"][-1].update(pcm_samples=32000, pcm_square_sum=32000 * 1000**2, pcm_peak=5000)
    trace_path, build_path = tmp_path / "trace.json", tmp_path / "build.json"
    trace_path.write_text(json.dumps(doc))
    build_path.write_text(json.dumps(BUILD))
    monkeypatch.setattr(sys, "argv", ["analyze.py", str(trace_path), "--build", str(build_path), "--require", check])
    assert module.main() == (2 if fault == "killed" else 1)
    report = json.loads(capsys.readouterr().out)
    assert report["checks"][check] == ("incomplete" if fault == "killed" else "failed")


@pytest.mark.parametrize("fault", ["zero_frames", "late_frame", "capture_error", "no_idle", "short_observation"])
def test_bad_capture_never_passes(fault):
    doc = trace()
    if fault == "zero_frames":
        for e in doc["events"]:
            e["frames"] = e["bytes"] = 0
    elif fault == "no_idle":
        doc["events"][-3]["state"] = "running"
    elif fault == "short_observation":
        doc["events"][-1]["elapsed_ms"] = 20500
    else:
        event = copy.deepcopy(doc["events"][-1])
        event["kind"] = fault
        doc["events"].insert(-1, event)
    assert module.analyze(doc, BUILD)["checks"]["start_stop"] == "failed"


def test_stalled_background_frames_fail_even_if_capture_eventually_resumes():
    doc = trace()
    for e in doc["events"]:
        if 6000 <= e["elapsed_ms"] <= 9000:
            e["frames"] = 50
            e["bytes"] = 50 * 320
    assert module.analyze(doc, BUILD)["checks"]["background_capture"] == "failed"


def test_separate_short_background_visits_do_not_add_up():
    doc = trace()
    for e in doc["events"]:
        if e["elapsed_ms"] == 8000:
            e["app_state"] = "active"
    assert module.analyze(doc, BUILD)["checks"]["background_capture"] == "not-observed"


@pytest.mark.parametrize("fault", ["stale_build", "backwards_clock", "backwards_count", "malformed_event"])
def test_bad_evidence_blocks(fault):
    doc = copy.deepcopy(trace())
    if fault == "stale_build":
        doc["build"]["git_sha"] = "c" * 40
    elif fault == "backwards_clock":
        doc["events"][-1]["elapsed_ms"] = 1
    elif fault == "backwards_count":
        doc["events"][-1]["frames"] = 0
    else:
        doc["events"][-1] = None
    with pytest.raises(ValueError):
        module.analyze(doc, BUILD)


def test_silent_pcm_does_not_pass_just_because_frames_arrive():
    doc = trace()
    doc["events"][-1].update(pcm_samples=32000, pcm_square_sum=0, pcm_peak=0)
    report = module.analyze(doc, BUILD)
    assert report["checks"]["start_stop"] == "passed"
    assert report["checks"]["non_silent_pcm"] == "failed"


def test_pcm_with_audible_energy_passes_signal_presence_check():
    doc = trace()
    doc["events"][-1].update(pcm_samples=32000, pcm_square_sum=32000 * 1000**2, pcm_peak=5000)
    report = module.analyze(doc, BUILD)
    assert report["checks"]["non_silent_pcm"] == "passed"
    assert -31 < report["rms_dbfs"] < -30


@pytest.mark.parametrize("energy", [float("nan"), float("inf"), -1])
def test_invalid_energy_is_rejected(energy):
    doc = trace()
    doc["events"][-1].update(pcm_samples=32000, pcm_square_sum=energy, pcm_peak=5000)
    with pytest.raises(ValueError):
        module.analyze(doc, BUILD)


def interruption_trace():
    doc = trace()
    original = doc["events"][7]
    for kind, ms, extra in [
        ("os_signal", 5001, {"signal": "interruptionBegan"}),
        ("state", 5002, {"state": "interrupted"}),
        ("os_signal", 5500, {"signal": "interruptionEnded", "should_resume": False}),
        ("state", 5501, {"state": "running"}),
    ]:
        event = dict(original, kind=kind, elapsed_ms=ms, **extra)
        doc["events"].append(event)
    doc["events"].sort(key=lambda e: e["elapsed_ms"])
    return doc


def test_real_interruption_oracle_accepts_recovered_delivery():
    report = module.analyze(interruption_trace(), BUILD)
    assert report["checks"]["interruption_recovery"] == "passed"
    assert report["interruption_recovery_ms"] == [500]


@pytest.mark.parametrize(
    "fault", ["missing_end", "missing_interrupted", "missing_running", "final_unrecovered", "slow_recovery"]
)
def test_interruption_absence_or_failure_cannot_pass(fault):
    doc = interruption_trace()
    if fault.startswith("missing_"):
        target = {
            "missing_end": ("signal", "interruptionEnded"),
            "missing_interrupted": ("state", "interrupted"),
            "missing_running": ("state", "running"),
        }[fault]
        doc["events"] = [e for e in doc["events"] if not (e.get(target[0]) == target[1] and e["elapsed_ms"] > 5000)]
    elif fault == "final_unrecovered":
        doc["events"].insert(-4, dict(doc["events"][-5], kind="os_signal", signal="interruptionBegan"))
    else:
        for e in doc["events"]:
            if 6000 <= e["elapsed_ms"] <= 11000:
                e["frames"] = 50
                e["bytes"] = 16000
    assert module.analyze(doc, BUILD)["checks"]["interruption_recovery"] != "passed"


def denied_trace():
    doc = trace()
    doc.update(run_id="denied", started_at="2026-09-22T01:00:00Z")
    events = []
    for kind, ms, extra in [
        ("start_requested", 0, {"permission": "denied"}),
        ("state", 1, {"state": "starting"}),
        ("state", 2, {"state": "idle"}),
        ("capture_error", 3, {"code": "permission_denied"}),
        ("start_failed", 4, {"code": "permission_denied", "permission": "denied"}),
        ("stop_requested", 5, {}),
        ("stop_completed", 6, {}),
        ("observation_completed", 2006, {}),
    ]:
        events.append(dict(kind=kind, elapsed_ms=ms, frames=0, bytes=0, app_state="active", **extra))
    doc["events"] = events
    return doc


def granted_trace():
    doc = trace()
    doc.update(run_id="granted", started_at="2026-09-22T01:01:00Z")
    doc["events"][2]["permission"] = "granted"
    return doc


def test_permission_denial_and_later_granted_capture_require_both_receipts():
    assert module.analyze(denied_trace(), BUILD)["checks"]["permission_denial"] == "passed"
    assert module.analyze(granted_trace(), BUILD)["checks"]["permission_recovery"] == "not-observed"
    assert module.analyze(granted_trace(), BUILD, denied_trace())["checks"]["permission_recovery"] == "passed"


@pytest.mark.parametrize(
    "fault",
    ["audio_while_denied", "unfinished_denial", "other_error", "wrong_build", "stale_restoration", "missing_granted"],
)
def test_permission_pair_mutations_cannot_pass(fault):
    before, after = denied_trace(), granted_trace()
    if fault == "audio_while_denied":
        before["events"][-1].update(frames=1, bytes=320)
    elif fault == "unfinished_denial":
        before["events"].pop()
    elif fault == "other_error":
        before["events"][3]["code"] = "unexpected_error"
    elif fault == "wrong_build":
        before["build"] = {"inputs": {"wrong": "build"}}
        with pytest.raises(ValueError):
            module.analyze(after, BUILD, before)
        return
    elif fault == "stale_restoration":
        after["started_at"] = before["started_at"]
    else:
        del after["events"][2]["permission"]
    assert module.analyze(after, BUILD, before)["checks"]["permission_recovery"] == "failed"


def sustained_trace():
    doc = trace()
    doc["requested_duration_seconds"] = 300
    samples = []
    for n in range(1, 300):
        samples.append(
            dict(
                kind="sample",
                elapsed_ms=n * 1000,
                frames=n * 10,
                bytes=n * 3200,
                app_state="active",
                cpu_seconds=n * 0.03,
                resident_bytes=32_000_000,
                interval_frame_gap_ms=100,
            )
        )
    terminal = []
    for e in doc["events"][-4:]:
        terminal.append(dict(e, elapsed_ms=e["elapsed_ms"] + 280000, frames=3000, bytes=960000))
    doc["events"] = doc["events"][:3] + samples + terminal
    return doc


def test_sustained_baseline_requires_full_duration_and_sampled_resources():
    result = module.analyze(sustained_trace(), BUILD)
    assert result["checks"]["sustained_capture"] == "passed"
    assert result["resources"]["mean_cpu_percent_one_core"] == pytest.approx(3)
    assert result["resources"]["resident_max_bytes"] == 32_000_000


@pytest.mark.parametrize("fault", ["short", "no_resources", "callback_gap", "sample_gap", "stalled"])
def test_sustained_baseline_mutations(fault):
    doc = sustained_trace()
    if fault == "short":
        for e in doc["events"]:
            e["elapsed_ms"] //= 2
    elif fault == "no_resources":
        del doc["events"][3]["cpu_seconds"]
    elif fault == "callback_gap":
        doc["events"][50]["interval_frame_gap_ms"] = 3000
    elif fault == "sample_gap":
        del doc["events"][50:55]
    else:
        doc["events"][50]["frames"] = doc["events"][49]["frames"]
    assert module.analyze(doc, BUILD)["checks"]["sustained_capture"] != "passed"


def test_bluetooth_permission_denial_requires_observed_authorization():
    spec = importlib.util.spec_from_file_location("ble_analyzer", PROBE.with_name("analyze_wearable.py"))
    ble = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ble)
    doc = dict(
        schema="omi-ble-radio-probe/v1",
        scope="corebluetooth-radio-only",
        audio_retained=False,
        build=BUILD,
        events=[
            dict(kind="bluetooth_state", elapsed_ms=0, packets=0, bytes=0, generation=0, state=4, authorization=2),
            dict(kind="completed", elapsed_ms=15000, packets=0, bytes=0, generation=0),
        ],
    )
    assert ble.analyze(doc, BUILD)["checks"]["permission_denial"] == "passed"
    doc["events"][0]["authorization"] = 0
    assert ble.analyze(doc, BUILD)["checks"]["permission_denial"] == "not-observed"


def test_bluetooth_permission_pair_requires_granted_packet_delivery():
    spec = importlib.util.spec_from_file_location("ble_fixture", Path(__file__).with_name("test_wearable_probe.py"))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    after = fixture.trace()
    after.update(run_id="ble-after", started_at="2026-09-22T02:01:00Z")
    after["events"].insert(
        0, dict(kind="bluetooth_state", elapsed_ms=0, packets=0, bytes=0, generation=0, state=5, authorization=3)
    )
    before = dict(
        schema=after["schema"],
        scope=after["scope"],
        audio_retained=False,
        build=fixture.BUILD,
        run_id="ble-before",
        started_at="2026-09-22T02:00:00Z",
        events=[
            dict(kind="bluetooth_state", elapsed_ms=0, packets=0, bytes=0, generation=0, state=4, authorization=2),
            dict(kind="completed", elapsed_ms=15000, packets=0, bytes=0, generation=0),
        ],
    )
    assert fixture.module.analyze(after, fixture.BUILD, before)["checks"]["permission_recovery"] == "passed"
    for fault in ("missing_grant", "stale", "no_delivery", "no_denial"):
        a, b = copy.deepcopy(after), copy.deepcopy(before)
        if fault == "missing_grant":
            a["events"][0]["authorization"] = 0
        elif fault == "stale":
            a["started_at"] = b["started_at"]
        elif fault == "no_delivery":
            a["events"] = [e for e in a["events"] if e["kind"] != "audio_started"]
        else:
            b["events"][0]["authorization"] = 0
        assert fixture.module.analyze(a, fixture.BUILD, b)["checks"]["permission_recovery"] == "failed"
