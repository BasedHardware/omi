import copy
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[3] / "app/ios/test/phone_mic_probe/analyze_wearable.py"
spec = importlib.util.spec_from_file_location("wearable_probe", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BUILD = {"inputs": {"probe.swift": "a" * 64}}


def trace():
    events = []
    for generation, offset in [(1, 0), (2, 10000)]:
        for i, kind in enumerate(
            [
                "connected",
                "services_discovered",
                "audio_characteristic_ready",
                "subscribe_requested",
                "subscribed",
                "audio_started",
                "sample",
            ]
        ):
            packets = (generation - 1) * 10 + (0 if i < 5 else 1 if i == 5 else 10)
            events.append(
                dict(
                    kind=kind,
                    elapsed_ms=offset + i * 100,
                    generation=generation,
                    packets=packets,
                    bytes=packets * 40,
                    app_state="foreground",
                )
            )
        if generation == 1:
            events.append(
                dict(
                    kind="disconnected",
                    expected=False,
                    elapsed_ms=1000,
                    generation=1,
                    packets=10,
                    bytes=400,
                    app_state="foreground",
                )
            )
    events.append(dict(kind="completed", elapsed_ms=12000, generation=2, packets=20, bytes=800, app_state="foreground"))
    return {
        "schema": "omi-ble-radio-probe/v1",
        "scope": "corebluetooth-radio-only",
        "audio_retained": False,
        "build": BUILD,
        "events": events,
    }


def test_reconnect_requires_actual_packet_delivery_after_service_discovery():
    r = module.analyze(trace(), BUILD)
    assert r["checks"]["packet_delivery"] == r["checks"]["reconnect_delivery"] == "passed"
    assert r["latencies"][1]["connected_to_audio_ms"] == 500


def test_truncated_radio_run_cannot_pass_any_capture_check():
    d = trace()
    d["events"].pop()  # No completed receipt after a device/process interruption.
    # Include an otherwise qualifying continuous background window too.
    last = d["events"][-1]
    for n in range(1, 13):
        d["events"].append(dict(last, kind="sample", elapsed_ms=last["elapsed_ms"] + n * 1000,
                                packets=20 + n, bytes=(20 + n) * 40, app_state="background"))
    checks = module.analyze(d, BUILD)["checks"]
    assert all(checks[name] != "passed" for name in ("packet_delivery", "reconnect_delivery", "background_delivery"))


def test_missing_audio_on_reconnect_fails_even_if_initial_link_streamed():
    d = trace()
    d["events"] = [e for e in d["events"] if not (e["generation"] == 2 and e["kind"] == "audio_started")]
    assert module.analyze(d, BUILD)["checks"]["reconnect_delivery"] == "failed"


def test_one_late_packet_does_not_prove_streaming_recovered():
    d = trace()
    for e in d["events"]:
        if e["generation"] == 2 and e["kind"] in ["sample", "completed"]:
            e["packets"] = 11
            e["bytes"] = 440
    assert module.analyze(d, BUILD)["checks"]["reconnect_delivery"] == "failed"


def test_unrecovered_final_disconnect_is_not_hidden_by_prior_reconnect():
    d = trace()
    event = copy.deepcopy(d["events"][-1])
    event.update(kind="disconnected", expected=False, elapsed_ms=11000)
    d["events"].insert(-1, event)
    assert module.analyze(d, BUILD)["checks"]["reconnect_delivery"] == "failed"


def test_audio_and_notification_confirmation_can_arrive_in_either_order():
    d = trace()
    for a, b in [(4, 5), (12, 13)]:
        d["events"][a]["kind"], d["events"][b]["kind"] = d["events"][b]["kind"], d["events"][a]["kind"]
    assert module.analyze(d, BUILD)["checks"]["reconnect_delivery"] == "passed"


def test_discovery_without_a_recording_is_not_a_pass():
    d = trace()
    d["events"] = [dict(kind="completed", elapsed_ms=1000, generation=0, packets=0, bytes=0)]
    assert module.analyze(d, BUILD)["checks"]["packet_delivery"] == "not-observed"


def test_stale_build_rejected():
    with pytest.raises(ValueError):
        module.analyze(trace(), {"inputs": {"probe.swift": "b" * 64}})


def test_backwards_time_rejected():
    d = trace()
    d["events"][-1]["elapsed_ms"] = 0
    with pytest.raises(ValueError):
        module.analyze(d, BUILD)
