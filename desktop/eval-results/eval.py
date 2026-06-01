#!/usr/bin/env python3
"""Monitor / compare Omi desktop query traces.

The QueryTracer writes one JSON object per query to ~/Library/Logs/Omi/traces.jsonl.
This summarizes recent queries and (optionally) diffs aggregate stats vs a saved baseline.

Usage:
  ./eval.py                       # summarize last 10 queries from the live trace log
  ./eval.py -n 25                 # last 25
  ./eval.py -f baseline-run5-extended.jsonl   # summarize a saved file instead
  ./eval.py --baseline baseline-run5-extended.jsonl   # live log vs baseline (aggregate diff)
  ./eval.py --quality             # also print query -> response excerpt (judge quality)

North-star metrics: input_tokens (deterministic, machine-independent) and ttft_ms.
"""
import argparse, json, os, statistics, sys
from pathlib import Path

LIVE = Path.home() / "Library/Logs/Omi/traces.jsonl"
HERE = Path(__file__).resolve().parent


def load(path):
    recs = []
    if not Path(path).exists():
        return recs
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return recs


def span_dur(rec, name):
    """Find a span by name anywhere in the (nested) span tree; return dur_ms or None."""
    def walk(spans):
        for s in spans or []:
            if s.get("name") == name:
                return s.get("dur_ms")
            r = walk(s.get("children"))
            if r is not None:
                return r
        return None
    return walk(rec.get("spans"))


def g(rec, *keys, default=None):
    for k in keys:
        if rec.get(k) is not None:
            return rec[k]
    return default


def sysprompt_chars(rec):
    sp = (rec.get("request") or {}).get("system_prompt")
    return len(sp) if isinstance(sp, str) else None


def summarize(recs, quality=False):
    if not recs:
        print("  (no records)")
        return
    hdr = f"{'#':>2}  {'in_tok':>7} {'out':>5} {'ttft_ms':>8} {'tps':>5} {'cache_r':>7} {'cost$':>7} {'shot':>4} {'shot_ms':>7} {'sys_ch':>7}  query"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for i, r in enumerate(recs, 1):
        req = r.get("request") or {}
        shot_ms = span_dur(r, "screenshot_capture")
        ttft = g(r, "ttft_ms", default=0) or 0
        tps = g(r, "tps", default=0) or 0
        cost = g(r, "cost_usd", default=0) or 0
        gaps = r.get("flagged_gaps") or []
        q = (r.get("query_text") or "").replace("\n", " ")[:42]
        print(f"{i:>2}  {g(r,'input_tokens',default=0):>7} {g(r,'output_tokens',default=0):>5} "
              f"{int(ttft):>8} {tps:>5.0f} {g(r,'cache_read_tokens',default=0):>7} "
              f"{cost:>7.4f} {('Y' if req.get('has_screenshot') else '-'):>4} "
              f"{(str(int(shot_ms)) if shot_ms else '-'):>7} {(str(sysprompt_chars(r)) if sysprompt_chars(r) else '-'):>7}  {q}")
        if gaps:
            for gp in gaps:
                print(f"        ⚠ gap {gp.get('gap_ms')}ms {gp.get('from')} → {gp.get('to')}")
        if quality:
            resp = (req.get("response_text") or "").replace("\n", " ")
            print(f"        ↳ {resp[:160]}")


def agg(recs, label):
    """Aggregate stats over first-query-like records (no/low history)."""
    it = [r["input_tokens"] for r in recs if r.get("input_tokens")]
    tt = [r["ttft_ms"] for r in recs if r.get("ttft_ms")]
    print(f"\n[{label}]  n={len(recs)}")
    if it:
        print(f"  input_tokens : min {min(it)}  median {int(statistics.median(it))}  max {max(it)}")
    if tt:
        print(f"  ttft_ms      : min {int(min(tt))}  median {int(statistics.median(tt))}  max {int(max(tt))}")
    return (statistics.median(it) if it else None, statistics.median(tt) if tt else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="last N records")
    ap.add_argument("-f", "--file", default=None, help="trace file (default: live log)")
    ap.add_argument("--baseline", default=None, help="baseline jsonl to diff aggregate vs")
    ap.add_argument("--quality", action="store_true", help="print response excerpts")
    args = ap.parse_args()

    src = Path(args.file) if args.file else LIVE
    if args.file and not src.is_absolute() and not src.exists():
        src = HERE / args.file
    recs = load(src)
    print(f"== {src} ==  ({len(recs)} total records, showing last {args.n})")
    summarize(recs[-args.n:], quality=args.quality)

    if args.baseline:
        bpath = Path(args.baseline)
        if not bpath.is_absolute() and not bpath.exists():
            bpath = HERE / args.baseline
        base = load(bpath)
        cur_med = agg(recs, f"current ({src.name})")
        base_med = agg(base, f"baseline ({bpath.name})")
        if cur_med[0] and base_med[0]:
            d = cur_med[0] - base_med[0]
            pct = 100 * d / base_med[0]
            print(f"\n  Δ input_tokens (median): {d:+.0f} ({pct:+.1f}%)")
        if cur_med[1] and base_med[1]:
            d = cur_med[1] - base_med[1]
            pct = 100 * d / base_med[1]
            print(f"  Δ ttft_ms (median)     : {d:+.0f} ({pct:+.1f}%)")


if __name__ == "__main__":
    main()
