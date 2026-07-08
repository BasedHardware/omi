#!/usr/bin/env python3
"""Aggregate omi QueryTracer traces for benchmarking.

Reads ~/Library/Logs/Omi/traces.jsonl (one JSON trace per line) and prints
median/p90 stats per metric, per span, and per flagged gap. Can save a labeled
snapshot and diff two snapshots (baseline vs optimized).

Examples:
  # Summarize the last 8 voice queries, dropping the cold first one:
  trace_stats.py --last 8 --mode voice_ptt_omni --drop-cold

  # Save a baseline snapshot:
  trace_stats.py --last 8 --mode voice_ptt_omni --drop-cold --label baseline --save baseline.json

  # After optimizing, snapshot again and diff:
  trace_stats.py --last 8 --mode voice_ptt_omni --drop-cold --label optimized --save optimized.json
  trace_stats.py --compare baseline.json optimized.json
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime

DEFAULT_LOG = os.path.expanduser("~/Library/Logs/Omi/traces.jsonl")

# Derived first so it leads the report — total minus speaking time (ptt_recording),
# the latency that actually matters for optimization (excludes how long you talked).
DERIVED = [("system_ms", "ms")]

SCALARS = [
    ("total_ms", "ms"),
    ("ttft_ms", "ms"),
    ("tps", ""),
    ("input_tokens", "tok"),
    ("output_tokens", "tok"),
    ("cache_read_tokens", "tok"),
    ("cache_write_tokens", "tok"),
    ("cost_usd", "$"),
]


def load(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def flatten_spans(spans, acc):
    for s in spans or []:
        acc.setdefault(s["name"], []).append(s["dur_ms"])
        flatten_spans(s.get("children"), acc)


def has_tool(t):
    """True if the trace involved any tool — either a ChatToolExecutor call
    (populates tool_executions) or an extension/UI tool (only a tool: span)."""
    if t.get("tool_executions"):
        return True
    names = {}
    flatten_spans(t.get("spans"), names)
    return any(n.startswith("tool:") for n in names)


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def span_dur(t, name):
    for s in t.get("spans", []):
        if s.get("name") == name:
            return s.get("dur_ms", 0)
    return 0


def summarize(traces, label=None):
    scalars = {}
    # system_ms = total minus speaking time (ptt_recording). For text queries
    # there is no ptt_recording so system_ms == total_ms.
    sys_vals = [t["total_ms"] - span_dur(t, "ptt_recording") for t in traces if t.get("total_ms") is not None]
    if sys_vals:
        scalars["system_ms"] = {
            "n": len(sys_vals),
            "median": round(statistics.median(sys_vals), 4),
            "p90": round(pctl(sys_vals, 0.9), 4),
            "min": round(min(sys_vals), 4),
            "max": round(max(sys_vals), 4),
        }
    for key, _unit in SCALARS:
        vals = [t[key] for t in traces if t.get(key) is not None]
        if vals:
            scalars[key] = {
                "n": len(vals),
                "median": round(statistics.median(vals), 4),
                "p90": round(pctl(vals, 0.9), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }
    span_acc = {}
    for t in traces:
        flatten_spans(t.get("spans"), span_acc)
    spans = {
        name: {"n": len(v), "median_ms": round(statistics.median(v))}
        for name, v in span_acc.items()
    }
    gap_acc = {}
    for t in traces:
        for g in t.get("flagged_gaps", []):
            gap_acc.setdefault(f'{g["from"]}->{g["to"]}', []).append(g["gap_ms"])
    gaps = {k: {"n": len(v), "median_ms": round(statistics.median(v))} for k, v in gap_acc.items()}
    return {"label": label, "count": len(traces), "scalars": scalars, "spans": spans, "gaps": gaps}


def fmt_summary(s):
    lines = [f"=== {s.get('label') or 'run'}  ({s['count']} traces) ==="]
    lines.append("-- metrics (median / p90) --")
    for key, unit in DERIVED + SCALARS:
        d = s["scalars"].get(key)
        if d:
            star = " *" if key == "system_ms" else ""
            lines.append(f"  {key:<20} {d['median']:>10}{unit:<4}  p90={d['p90']}{unit}  (n={d['n']}){star}")
    lines.append("-- spans (median dur, by start order is not preserved) --")
    for name, d in sorted(s["spans"].items(), key=lambda kv: -kv[1]["median_ms"]):
        lines.append(f"  {name:<22} {d['median_ms']:>8} ms   (n={d['n']})")
    if s["gaps"]:
        lines.append("-- flagged gaps (median) --")
        for name, d in sorted(s["gaps"].items(), key=lambda kv: -kv[1]["median_ms"]):
            lines.append(f"  {name:<34} {d['median_ms']:>8} ms   (n={d['n']})")
    return "\n".join(lines)


def diff(a, b):
    lines = [f"=== diff: {a.get('label') or 'A'}  ->  {b.get('label') or 'B'} ==="]
    lines.append(f"  traces: {a['count']} -> {b['count']}")
    lines.append("-- metrics (median) --")
    for key, unit in DERIVED + SCALARS:
        da, db = a["scalars"].get(key), b["scalars"].get(key)
        if da and db:
            delta = db["median"] - da["median"]
            pct = (delta / da["median"] * 100) if da["median"] else 0
            arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "=")
            lines.append(
                f"  {key:<20} {da['median']:>10}{unit:<3} -> {db['median']:>10}{unit:<3}  {arrow}{abs(delta):.2f}{unit} ({pct:+.0f}%)"
            )
    lines.append("-- spans (median ms) --")
    names = sorted(set(a["spans"]) | set(b["spans"]))
    for name in names:
        ma = a["spans"].get(name, {}).get("median_ms")
        mb = b["spans"].get(name, {}).get("median_ms")
        if ma is None:
            lines.append(f"  {name:<22} {'—':>8} -> {mb:>8}  (new)")
        elif mb is None:
            lines.append(f"  {name:<22} {ma:>8} -> {'—':>8}  (gone)")
        else:
            d = mb - ma
            arrow = "↓" if d < 0 else ("↑" if d > 0 else "=")
            lines.append(f"  {name:<22} {ma:>8} -> {mb:>8}  {arrow}{abs(d)} ms")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=DEFAULT_LOG, help="traces.jsonl path")
    ap.add_argument("--last", type=int, help="only the last N traces")
    ap.add_argument("--since", help="ISO8601; only traces with timestamp >= this")
    ap.add_argument("--mode", help="filter by input_mode (e.g. voice_ptt_omni, text)")
    ap.add_argument("--no-tools", action="store_true", help="only traces with no tool calls (clean pipeline)")
    ap.add_argument("--tools-only", action="store_true", help="only traces that made a tool call")
    ap.add_argument("--no-shot", action="store_true", help="only traces with no screenshot captured")
    ap.add_argument("--shot", action="store_true", help="only traces that captured a screenshot")
    ap.add_argument("--drop-cold", action="store_true", help="drop the first (cold) trace in the selection")
    ap.add_argument("--label", help="label for the snapshot")
    ap.add_argument("--save", help="write the summary JSON to this path")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="diff two saved snapshot JSONs")
    args = ap.parse_args()

    if args.compare:
        with open(args.compare[0]) as f:
            a = json.load(f)
        with open(args.compare[1]) as f:
            b = json.load(f)
        print(diff(a, b))
        return

    traces = load(args.log)
    if args.mode:
        traces = [t for t in traces if t.get("input_mode") == args.mode]
    if args.no_tools:
        traces = [t for t in traces if not has_tool(t)]
    if args.tools_only:
        traces = [t for t in traces if has_tool(t)]
    if args.no_shot:
        traces = [t for t in traces if not (t.get("request") or {}).get("has_screenshot")]
    if args.shot:
        traces = [t for t in traces if (t.get("request") or {}).get("has_screenshot")]
    if args.since:
        traces = [t for t in traces if t.get("timestamp", "") >= args.since]
    if args.last:
        traces = traces[-args.last:]
    if args.drop_cold and traces:
        traces = traces[1:]
    if not traces:
        print("no traces matched", file=sys.stderr)
        sys.exit(1)

    s = summarize(traces, label=args.label)
    print(fmt_summary(s))
    if args.save:
        with open(args.save, "w") as f:
            json.dump(s, f, indent=2)
        print(f"\nsaved -> {args.save}")


if __name__ == "__main__":
    main()
