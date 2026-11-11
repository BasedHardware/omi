#!/usr/bin/env python3
"""Replay storm policies on 5-minute Monitoring aggregates; never modifies GCP."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

STEP = dt.timedelta(minutes=5)
UTC = dt.timezone.utc


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def first_fire(points, threshold, duration, start, end):
    """Conservative sampled dwell: require duration between violating samples."""
    since = previous = None
    for time, value in sorted(points.items()):
        if not start <= time < end:
            continue
        if previous is not None and time - previous != STEP:
            since = None
        previous = time
        if value is None or value <= threshold:
            since = None
        elif since is None:
            since = time
        if since is not None and time - since >= duration:
            return time.isoformat().replace("+00:00", "Z")
    return "none"


def load(path):
    payload = json.loads(Path(path).read_text())
    if payload.get("nextPageToken"):
        raise ValueError("Incomplete Monitoring history: fetch all pages before replay")
    if "error" in payload or "timeSeries" not in payload:
        raise ValueError("Monitoring request failed or returned no series")
    return payload["timeSeries"]


def replay(edge, sync, windows=None):
    edges = {}
    for series in edge:
        backend = series["resource"]["labels"]["backend_target_name"]
        edges[backend] = {
            timestamp(p["interval"]["endTime"]): float(p["value"]["doubleValue"]) * 60 for p in series["points"]
        }
    totals, duplicates = {}, {}
    for series in sync:
        for point in series["points"]:
            time = timestamp(point["interval"]["endTime"])
            value = int(point["value"]["int64Value"])
            totals[time] = totals.get(time, 0) + value
            if series["metric"]["labels"]["response_code"] == "409":
                duplicates[time] = duplicates.get(time, 0) + value
    # Use exactly the 300s ALIGN_SUM counts returned by Monitoring, with
    # no homemade one-hour rolling reconstruction. Both ratio and volume
    # conditions have the same one-hour duration, so their AND is equivalent
    # to requiring both thresholds for the entire sampled retest interval.
    configs = Path(__file__).resolve().parent.parent / "monitoring"
    edge_threshold = json.loads((configs / "api_edge_429_policy.json").read_text())["conditions"][0]["conditionThreshold"]
    sync_policy = json.loads((configs / "sync_upload_409_policy.json").read_text())
    ratio_threshold, volume_threshold = [c["conditionThreshold"] for c in sync_policy["conditions"]]
    if sync_policy["combiner"] != "AND":
        raise ValueError("Replay requires ratio AND denominator volume")
    for condition in (edge_threshold, ratio_threshold, volume_threshold):
        if condition["aggregations"][0]["alignmentPeriod"] != "300s":
            raise ValueError("Replay requires 300s Monitoring aggregates")
    if ratio_threshold["duration"] != volume_threshold["duration"]:
        raise ValueError("Replay requires matching ratio and volume durations")
    ratios = {time: 100 * duplicates.get(time, 0) / total if total else None for time, total in totals.items()}
    qualified = {
        time: ratio if totals[time] > volume_threshold["thresholdValue"] else None for time, ratio in ratios.items()
    }
    windows = windows or [
        ("baseline", "2026-09-21T04:00:00Z", "2026-10-07T12:00:00Z"),
        ("incident", "2026-10-07T12:00:00Z", "2026-10-11T17:00:00Z"),
        ("post-fix", "2026-10-11T17:00:00Z", "2026-10-12T04:00:00Z"),
    ]
    print("| Window (UTC) | Series | Peak aligned value | First eligible fire (UTC) |")
    print("| --- | --- | ---: | --- |")
    for label, start, end in windows:
        start, end = timestamp(start), timestamp(end)
        for backend, points in edges.items():
            values = [v for t, v in points.items() if start <= t < end]
            peak = max(values, default=0)
            fire = first_fire(points, edge_threshold["thresholdValue"] * 60, dt.timedelta(seconds=int(edge_threshold["duration"][:-1])), start, end)
            print(f"| {label} | {backend} | {peak:.1f}/min | {fire} |")
        eligible_values = [v for t, v in qualified.items() if start <= t < end and v is not None]
        fire = first_fire(qualified, ratio_threshold["thresholdValue"] * 100,
                          dt.timedelta(seconds=int(ratio_threshold["duration"][:-1])), start, end)
        print(f"| {label} | sync 409 share (5m; volume-qualified) | {max(eligible_values, default=0):.2f}% | {fire} |")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge", required=True)
    parser.add_argument("--sync", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must be supplied together")
    windows = [("selected", args.start, args.end)] if args.start else None
    replay(load(args.edge), load(args.sync), windows)


if __name__ == "__main__":
    main()
