#!/usr/bin/env python3
"""Check a native iPhone trace offline; never equate missing scenarios with pass."""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path


def analyze(trace, expected_build, permission_before=None):
    if not isinstance(trace, dict) or trace.get("schema") != "phone-mic-device-probe/v1":
        raise ValueError("unsupported probe trace")
    if trace.get("build") != expected_build or not expected_build.get("inputs"):
        raise ValueError("trace build does not match the selected build manifest")
    if trace.get("audio_retained") is not False or trace.get("scope") != "native-stream-only":
        raise ValueError("trace scope must be native stream metadata without retained audio")
    events = trace.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("no events recorded")
    previous = {"elapsed_ms": 0, "frames": 0, "bytes": 0}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
            raise ValueError("malformed event")
        for key in ("elapsed_ms", "frames", "bytes"):
            value = event.get(key)
            if type(value) is not int or value < previous[key]:
                raise ValueError(f"{key} must be a nonnegative monotonic integer")
        if event.get("app_state") not in ("active", "inactive", "background"):
            raise ValueError("missing app state")
        previous = event
    kinds = [e["kind"] for e in events]
    outcomes = {}
    errors = {
        "capture_error",
        "start_failed",
        "wrong_session",
        "unexpected_batch_progress",
        "late_frame",
        "observation_expired",
    } & set(kinds)
    if any(e.get("session_id", trace.get("session_id")) != trace.get("session_id") for e in events):
        errors.add("wrong_session")
    required = ["start_requested", "start_completed", "stop_requested", "stop_completed", "observation_completed"]
    complete = all(kinds.count(k) == 1 for k in required)
    if complete:
        positions = [kinds.index(k) for k in required]
        complete = positions == sorted(positions) and kinds[-1] == "observation_completed"
    if not complete:
        outcomes["start_stop"] = "failed" if errors else "incomplete"
    else:
        start, stop, end = (
            events[kinds.index(k)] for k in ("start_completed", "stop_completed", "observation_completed")
        )
        captured = stop["frames"] > 0 and stop["bytes"] > 0 and stop["elapsed_ms"] - start["elapsed_ms"] >= 10000
        quiet = end["elapsed_ms"] - stop["elapsed_ms"] >= 1900 and end["frames"] == stop["frames"]
        states = [e.get("state") for e in events if e["kind"] == "state"]
        outcomes["start_stop"] = (
            "passed"
            if captured and quiet and not errors and "running" in states and states[-1:] == ["idle"]
            else "failed"
        )

    samples = [e for e in events if e["kind"] == "sample"]
    # Split on every foreground sample. Do not combine separate short visits
    # to the background into a fictitious long continuous capture.
    groups = []
    for sample in samples:
        if sample["app_state"] == "background":
            if not groups or groups[-1] is None:
                groups.append([])
            groups[-1].append(sample)
        elif groups and groups[-1] is not None:
            groups.append(None)
    qualified = [g for g in groups if g and g[-1]["elapsed_ms"] - g[0]["elapsed_ms"] >= 10000]
    outcomes["background_capture"] = "not-observed"
    outcomes["foreground_recovery"] = "not-observed"
    if qualified:
        continuous = all(
            b["frames"] > a["frames"] and b["bytes"] > a["bytes"] and b["elapsed_ms"] - a["elapsed_ms"] <= 2500
            for g in qualified
            for a, b in zip(g, g[1:])
        )
        outcomes["background_capture"] = "passed" if continuous and not errors else "failed"
        returns = []
        for group in qualified:
            last = group[-1]
            after = next(
                (s for s in samples if s["elapsed_ms"] > last["elapsed_ms"] and s["app_state"] == "active"), None
            )
            if after:
                returns.append(after["frames"] > last["frames"] and after["elapsed_ms"] - last["elapsed_ms"] <= 5000)
        if returns:
            outcomes["foreground_recovery"] = "passed" if all(returns) and not errors else "failed"
    # Optional acoustic measurement; old frame-only traces remain unqualified
    # here. This checks non-silent PCM, not speech intelligibility or quality.
    outcomes["non_silent_pcm"] = "not-observed"
    rms_dbfs = None
    end = events[-1]
    if all(k in end for k in ("pcm_samples", "pcm_square_sum", "pcm_peak")):
        n, squares, peak = end["pcm_samples"], end["pcm_square_sum"], end["pcm_peak"]
        if (
            type(n) is not int
            or n < 0
            or not isinstance(squares, (int, float))
            or not math.isfinite(squares)
            or squares < 0
        ):
            raise ValueError("invalid PCM energy measurement")
        if type(peak) is not int or not 0 <= peak <= 32768:
            raise ValueError("invalid PCM peak")
        if n > 0 and squares > 0:
            rms_dbfs = 10 * math.log10(squares / n / (32768**2))
        outcomes["non_silent_pcm"] = "passed" if rms_dbfs is not None and rms_dbfs > -60 and peak > 100 else "failed"
    # Reviewed oracle: each real interruption begins from delivering audio,
    # enters interrupted, ends, returns to running and delivers NEW audio
    # within five seconds. Every occurrence must recover before final stop.
    interruptions = [i for i, e in enumerate(events) if e.get("signal") == "interruptionBegan"]
    outcomes["interruption_recovery"] = "not-observed"
    recovery_ms = []
    for i in interruptions:
        begin = events[i]
        boundary = next(
            (
                j
                for j in range(i + 1, len(events))
                if events[j].get("signal") == "interruptionBegan" or events[j]["kind"] == "stop_requested"
            ),
            len(events),
        )
        seq = events[i + 1 : boundary]
        ended = next((e for e in seq if e.get("signal") == "interruptionEnded"), None)
        interrupted = next((e for e in seq if e.get("state") == "interrupted"), None)
        running = next(
            (e for e in seq if e.get("state") == "running" and ended and e["elapsed_ms"] >= ended["elapsed_ms"]), None
        )
        delivered = next(
            (
                e
                for e in seq
                if e["kind"] == "sample"
                and running
                and e["elapsed_ms"] > running["elapsed_ms"]
                and e["frames"] > running["frames"]
                and e["bytes"] > running["bytes"]
            ),
            None,
        )
        okay = (
            begin["frames"] > 0
            and ended
            and interrupted
            and running
            and delivered
            and interrupted["elapsed_ms"] <= ended["elapsed_ms"]
            and delivered["elapsed_ms"] - ended["elapsed_ms"] <= 5000
        )
        if delivered and ended:
            recovery_ms.append(delivered["elapsed_ms"] - ended["elapsed_ms"])
        outcome = "passed" if okay and outcomes["start_stop"] == "passed" else "failed" if complete else "incomplete"
        if outcomes["interruption_recovery"] != "failed":
            outcomes["interruption_recovery"] = outcome

    denied = [
        e
        for e in events
        if e["kind"] == "start_failed" and e.get("code") == "permission_denied" and e.get("permission") == "denied"
    ]
    outcomes["permission_denial"] = "not-observed"
    if denied:
        allowed_errors = {"capture_error", "start_failed"}
        denial_order = ["start_requested", "start_failed", "stop_requested", "stop_completed", "observation_completed"]
        denial_complete = (
            all(kinds.count(k) == 1 for k in denial_order) and len(denied) == 1 and kinds[-1] == "observation_completed"
        )
        if denial_complete:
            positions = [kinds.index(k) for k in denial_order]
            denial_complete = positions == sorted(positions)
        stop = next((e for e in events if e["kind"] == "stop_completed"), None)
        expected_errors = all(e.get("code") == "permission_denied" for e in events if e["kind"] == "capture_error")
        okay = (
            denial_complete
            and stop
            and end["elapsed_ms"] - stop["elapsed_ms"] >= 1900
            and end["frames"] == end["bytes"] == 0
            and "start_completed" not in kinds
            and expected_errors
            and not (errors - allowed_errors)
            and not any(e.get("state") == "running" for e in events)
        )
        outcomes["permission_denial"] = "passed" if okay else "failed"
    outcomes["permission_recovery"] = "not-observed"
    if permission_before is not None:
        before = analyze(permission_before, expected_build)
        try:
            chronological = datetime.fromisoformat(trace["started_at"].replace("Z", "+00:00")) > datetime.fromisoformat(
                permission_before["started_at"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError, TypeError):
            raise ValueError("permission pair requires valid ordered start timestamps")
        restored = any(e["kind"] == "start_completed" and e.get("permission") == "granted" for e in events)
        outcomes["permission_recovery"] = (
            "passed"
            if (
                chronological
                and trace.get("run_id") != permission_before.get("run_id")
                and before["checks"]["permission_denial"] == "passed"
                and restored
                and outcomes["start_stop"] == "passed"
            )
            else "failed"
        )

    resources = resource_summary(samples, "frames", "interval_frame_gap_ms")
    outcomes["sustained_capture"] = "not-observed"
    if trace.get("requested_duration_seconds", 0) >= 300:
        duration = (
            events[kinds.index("stop_requested")]["elapsed_ms"] - events[kinds.index("start_completed")]["elapsed_ms"]
            if "stop_requested" in kinds and "start_completed" in kinds
            else 0
        )
        outcomes["sustained_capture"] = (
            "passed"
            if (
                duration >= 295000
                and outcomes["start_stop"] == "passed"
                and resources
                and resources["sample_span_ms"] >= 290000
                and resources["continuous_delivery"]
                and resources["max_delivery_gap_ms"] <= 2500
            )
            else "failed" if complete else "incomplete"
        )
    # A subset selected with --require must not qualify a killed or otherwise
    # failed run just because it contains an earlier successful sample window.
    for name in ("background_capture", "foreground_recovery", "non_silent_pcm"):
        if outcomes[name] == "passed" and outcomes["start_stop"] != "passed":
            outcomes[name] = outcomes["start_stop"]
    return {
        "schema": "phone-mic-probe-analysis/v1",
        "scope": "native-stream-only",
        "run_id": trace.get("run_id"),
        "git_sha": expected_build.get("git_sha"),
        "checks": outcomes,
        "errors": sorted(errors),
        "frames": events[-1]["frames"],
        "duration_ms": events[-1]["elapsed_ms"],
        "rms_dbfs": rms_dbfs,
        "interruption_recovery_ms": recovery_ms,
        "resources": resources,
    }


def resource_summary(samples, counter, gap_key):
    if not samples or not all(all(k in e for k in ("resident_bytes", "cpu_seconds", gap_key)) for e in samples):
        return None
    for e in samples:
        for key in ("resident_bytes", "cpu_seconds", gap_key):
            if type(e[key]) not in (int, float) or not math.isfinite(e[key]) or e[key] < 0:
                raise ValueError("invalid resource measurement")
    if any(b["cpu_seconds"] < a["cpu_seconds"] for a, b in zip(samples, samples[1:])):
        raise ValueError("CPU counter regressed")
    span = samples[-1]["elapsed_ms"] - samples[0]["elapsed_ms"]
    return {
        "sample_span_ms": span,
        "sample_count": len(samples),
        "resident_first_bytes": samples[0]["resident_bytes"],
        "resident_last_bytes": samples[-1]["resident_bytes"],
        "resident_max_bytes": max(e["resident_bytes"] for e in samples),
        "mean_cpu_percent_one_core": (
            (samples[-1]["cpu_seconds"] - samples[0]["cpu_seconds"]) * 100000 / span if span else None
        ),
        "max_delivery_gap_ms": max(e[gap_key] for e in samples),
        "continuous_delivery": len(samples) > 1
        and all(
            b[counter] > a[counter] and b["bytes"] > a["bytes"] and 0 < b["elapsed_ms"] - a["elapsed_ms"] <= 2500
            for a, b in zip(samples, samples[1:])
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--build", required=True, type=Path, help="build.json from the installed probe artifact")
    parser.add_argument("--permission-before", type=Path, help="completed denied attempt from the same build")
    parser.add_argument(
        "--require",
        action="append",
        choices=[
            "start_stop",
            "background_capture",
            "foreground_recovery",
            "non_silent_pcm",
            "interruption_recovery",
            "permission_denial",
            "permission_recovery",
            "sustained_capture",
        ],
    )
    args = parser.parse_args()
    try:
        report = analyze(
            json.loads(args.trace.read_text()),
            json.loads(args.build.read_text()),
            json.loads(args.permission_before.read_text()) if args.permission_before else None,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    selected = [report["checks"][k] for k in (args.require or ["start_stop"])]
    return 1 if "failed" in selected else 0 if all(v == "passed" for v in selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
