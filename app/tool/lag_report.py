#!/usr/bin/env python3
"""Summarize the lag capture in an Omi mobile debug log.

Usage: python3 app/tool/lag_report.py omi_debug_YYYYMMDD.log [more.log ...]

The app writes `mobile_lag_*` events to its local debug log while
Settings -> Developer -> Debug logs is on (see app/lib/utils/analytics/lag_recorder.dart).
This prints which surfaces lag, whether the UI thread (build) or the raster
thread is the bottleneck, whether it happens while scrolling, after a tap or
idle, the worst frames with timestamps, slow taps and UI-isolate stalls.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

COUNTS = (
    "frames", "slow_frames", "severe_frames", "freezes", "build_bound", "raster_bound",
    "slow_while_scrolling", "slow_after_tap", "slow_idle", "taps", "slow_taps", "stalls",
)
MAXES = ("worst_frame_ms", "worst_tap_ms", "worst_stall_ms")


def events(paths):
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if '"mobile_lag_' not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                # The app logs these as mobile_render_diagnostic events named by their `event` field.
                kind = str(event.get("event") or event.get("type", ""))
                if kind.startswith("mobile_lag_"):
                    event["type"] = kind
                    yield event


def main(paths) -> int:
    surfaces = defaultdict(lambda: defaultdict(float))
    frames, stalls, taps = {}, {}, {}
    reports = 0
    for event in events(paths):
        kind = event["type"]
        if kind == "mobile_lag_report":
            reports += 1
            for row in event.get("surfaces", []):
                acc = surfaces[row.get("surface", "?")]
                for key in COUNTS:
                    acc[key] += row.get(key, 0) or 0
                for key in MAXES:
                    acc[key] = max(acc[key], row.get(key, 0) or 0)
                acc["build_ms_sum"] += (row.get("mean_build_ms", 0) or 0) * (row.get("frames", 0) or 0)
                acc["raster_ms_sum"] += (row.get("mean_raster_ms", 0) or 0) * (row.get("frames", 0) or 0)
            for row in event.get("worst_frames", []):
                frames[(row.get("at"), row.get("surface"))] = row
            for row in event.get("worst_stalls", []):
                stalls[(row.get("at"), row.get("surface"))] = row
            for row in event.get("slowest_taps", []):
                taps[(row.get("at"), row.get("surface"))] = row
        elif kind == "mobile_lag_frame":
            frames[(event.get("at"), event.get("surface"))] = event
        elif kind == "mobile_lag_stall":
            stalls[(event.get("at"), event.get("surface"))] = event
        elif kind == "mobile_lag_tap":
            taps[(event.get("at"), event.get("surface"))] = event

    if not surfaces and not frames and not stalls and not taps:
        print("No lag capture found. Turn on Settings -> Developer -> Debug logs, background and reopen the app,")
        print("use it until it lags, background the app once, then share the log.")
        return 1

    print(f"# Lag capture ({reports} report(s))\n")
    if surfaces:
        print("## Surfaces, most slow frames first\n")
        print("| surface | frames | slow % | severe | freezes | build/raster bound | scroll/tap/idle | worst ms "
              "| mean build/raster ms | slow taps | worst tap ms | stalls | worst stall ms |")
        print("|---|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|")
        ranked = sorted(surfaces.items(), key=lambda kv: kv[1]["slow_frames"], reverse=True)
        for name, s in ranked:
            n = s["frames"] or 1
            print(
                f"| {name} | {int(s['frames'])} | {100 * s['slow_frames'] / n:.1f} | {int(s['severe_frames'])} "
                f"| {int(s['freezes'])} | {int(s['build_bound'])}/{int(s['raster_bound'])} "
                f"| {int(s['slow_while_scrolling'])}/{int(s['slow_after_tap'])}/{int(s['slow_idle'])} "
                f"| {s['worst_frame_ms']:.1f} | {s['build_ms_sum'] / n:.1f}/{s['raster_ms_sum'] / n:.1f} "
                f"| {int(s['slow_taps'])}/{int(s['taps'])} | {s['worst_tap_ms']:.1f} | {int(s['stalls'])} "
                f"| {s['worst_stall_ms']:.1f} |"
            )
        print()
        print("Reading it: build-bound slow frames are UI-isolate work (rebuilds, layout, sync decode/sort);")
        print("raster-bound ones are GPU work (saveLayer from opacity/clips/blur, shadows, big images).")
        print("Stalls are UI-isolate blocks between frames; slow taps include the tap handler's sync work.\n")

    def table(title, rows, columns, key):
        if not rows:
            return
        print(f"## {title}\n")
        print("| " + " | ".join(columns) + " |")
        print("|" + "---|" * len(columns))
        for row in sorted(rows.values(), key=lambda r: r.get(key, 0) or 0, reverse=True)[:25]:
            print("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
        print()

    table("Worst frames", frames, ["at", "surface", "interaction", "bound", "build_ms", "raster_ms", "total_ms"],
          "total_ms")
    table("Slowest taps (tap to end of next frame's UI work)", taps, ["at", "surface", "tap_to_frame_ms"],
          "tap_to_frame_ms")
    table("UI-isolate stalls", stalls, ["at", "surface", "interaction", "blocked_ms"], "blocked_ms")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
