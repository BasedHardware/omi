#!/usr/bin/env python3
"""Qualify only observed CoreBluetooth packet delivery and reconnect events."""

import argparse
import json
from datetime import datetime
from pathlib import Path


def analyze(trace, build, permission_before=None):
    if trace.get("schema") != "omi-ble-radio-probe/v1" or trace.get("scope") != "corebluetooth-radio-only":
        raise ValueError("unsupported radio trace")
    if trace.get("audio_retained") is not False or trace.get("build") != build or not build.get("inputs"):
        raise ValueError("audio retention or build identity mismatch")
    events = trace.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("missing events")
    previous = {k: 0 for k in ("elapsed_ms", "packets", "bytes", "generation")}
    for e in events:
        if not isinstance(e, dict) or not isinstance(e.get("kind"), str):
            raise ValueError("malformed event")
        for k in ("elapsed_ms", "packets", "bytes", "generation"):
            if type(e.get(k)) is not int or e[k] < previous[k]:
                raise ValueError(f"nonmonotonic or invalid {k}")
        previous = e
    kinds = [e["kind"] for e in events]
    complete = kinds.count("completed") == 1
    completion = next((e for e in events if e["kind"] == "completed"), None)
    errors = sorted({e["kind"] for e in events if e["kind"].endswith("_failed") or e["kind"] == "notification_error"})
    if complete and any(
        e["packets"] != completion["packets"] for e in events if e["elapsed_ms"] > completion["elapsed_ms"]
    ):
        errors.append("packets_after_completion")
    connections = [e for e in events if e["kind"] == "connected"]
    checks = {
        "packet_delivery": "not-observed",
        "reconnect_delivery": "not-observed",
        "background_delivery": "not-observed",
    }
    latencies = []
    for connection in connections:
        generation = connection["generation"]
        seq = [e for e in events if e["generation"] == generation and e["elapsed_ms"] >= connection["elapsed_ms"]]
        required = ["connected", "services_discovered", "audio_characteristic_ready", "subscribe_requested"]
        order = [e["kind"] for e in seq]
        valid = all(order.count(k) == 1 for k in required)
        if valid:
            positions = [order.index(k) for k in required]
            valid = positions == sorted(positions)
            valid = valid and all(
                order.count(k) == 1 and order.index(k) > positions[-1] for k in ("subscribed", "audio_started")
            )
        audio = next((e for e in seq if e["kind"] == "audio_started"), None)
        delta = audio["elapsed_ms"] - connection["elapsed_ms"] if audio else None
        # Sampled bytes must continue beyond a single stale initial packet.
        continued = audio and any(
            e["kind"] == "sample" and e["packets"] > audio["packets"] and e["bytes"] > audio["bytes"] for e in seq
        )
        passed = valid and continued and delta <= 10000 and not errors
        name = "packet_delivery" if generation == 1 else "reconnect_delivery"
        outcome = "passed" if passed and complete else "incomplete" if passed else "failed"
        if checks[name] != "failed":
            checks[name] = outcome
        if generation > 1:
            prior_disconnect = any(
                e["kind"] == "disconnected"
                and e.get("expected") is False
                and e["generation"] == generation - 1
                and e["elapsed_ms"] < connection["elapsed_ms"]
                for e in events
            )
            if not prior_disconnect:
                checks[name] = "failed"
        latencies.append({"generation": generation, "connected_to_audio_ms": delta})
    # Every unexpected disconnect must recover; do not hide a final failed
    # recovery behind a successful earlier reconnect.
    for lost in (e for e in events if e["kind"] == "disconnected" and e.get("expected") is False):
        recovered = any(
            c["generation"] == lost["generation"] + 1 and c["elapsed_ms"] > lost["elapsed_ms"] for c in connections
        )
        if not recovered:
            checks["reconnect_delivery"] = "failed" if complete else "incomplete"
    samples = [e for e in events if e["kind"] == "sample"]
    groups = [[]]
    for s in samples:
        if s.get("app_state") == "background":
            groups[-1].append(s)
        elif groups[-1]:
            groups.append([])
    long_groups = [g for g in groups if len(g) > 1 and g[-1]["elapsed_ms"] - g[0]["elapsed_ms"] >= 10000]
    if long_groups:
        okay = all(
            b["packets"] > a["packets"] and b["elapsed_ms"] - a["elapsed_ms"] <= 2500
            for g in long_groups
            for a, b in zip(g, g[1:])
        )
        checks["background_delivery"] = "passed" if okay and complete and not errors else "failed"
    if errors:
        checks["packet_delivery"] = "failed"
    denied = [e for e in events if e["kind"] == "bluetooth_state" and e.get("authorization") == 2]
    checks["permission_denial"] = "not-observed"
    if denied:
        checks["permission_denial"] = (
            "passed"
            if (
                complete
                and kinds[-1] == "completed"
                and not connections
                and not errors
                and events[-1]["packets"] == events[-1]["bytes"] == 0
                and not any(e.get("authorization") == 3 for e in events)
            )
            else "failed"
        )
    checks["permission_recovery"] = "not-observed"
    if permission_before is not None:
        before = analyze(permission_before, build)
        try:
            chronological = datetime.fromisoformat(trace["started_at"].replace("Z", "+00:00")) > datetime.fromisoformat(
                permission_before["started_at"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError, TypeError):
            raise ValueError("permission pair requires valid ordered start timestamps")
        granted = any(
            e["kind"] == "bluetooth_state" and e.get("authorization") == 3 and e.get("state") == 5 for e in events
        )
        checks["permission_recovery"] = (
            "passed"
            if (
                chronological
                and trace.get("run_id") != permission_before.get("run_id")
                and before["checks"]["permission_denial"] == "passed"
                and granted
                and checks["packet_delivery"] == "passed"
            )
            else "failed"
        )
    return {
        "schema": "omi-ble-radio-analysis/v1",
        "scope": "corebluetooth-radio-only",
        "run_id": trace.get("run_id"),
        "checks": checks,
        "errors": errors,
        "packets": events[-1]["packets"],
        "bytes": events[-1]["bytes"],
        "connections": len(connections),
        "latencies": latencies,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--permission-before", type=Path)
    p.add_argument(
        "--require",
        action="append",
        choices=[
            "packet_delivery",
            "reconnect_delivery",
            "background_delivery",
            "permission_denial",
            "permission_recovery",
        ],
    )
    args = p.parse_args()
    try:
        report = analyze(
            json.loads(args.trace.read_text()),
            json.loads(args.build.read_text()),
            json.loads(args.permission_before.read_text()) if args.permission_before else None,
        )
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as e:
        print(json.dumps({"status": "blocked", "reason": str(e)}))
        return 2
    print(json.dumps(report, indent=2))
    selected = [report["checks"][k] for k in (args.require or ["packet_delivery", "reconnect_delivery"])]
    return 1 if "failed" in selected else 0 if all(v == "passed" for v in selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
