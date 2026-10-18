#!/usr/bin/env python3
"""Build an executive Markdown digest from Omi goal JSON exports.

See goals_digest.md for the full recipe.

Usage:
    omi --json goal list > goals.json
    python goals_digest.py goals.json [goals2.json ...] omi_goals_digest.md

Accepts one or more export pages; each goal ID is counted once. KPIs cover
total / active / inactive / achieved (>=100% of target) / average progress,
plus a per-goal-type breakdown table and per-goal status indicators.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("goals", "items", "data")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def one_line(value: Any) -> str:
    """Render a loosely typed field as one line of text; coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(strip_surrogates(value).split())


def number(value: Any) -> Optional[float]:
    """Loose numeric coercion for metric fields; non-numeric → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_num(value: float) -> str:
    """Compact number formatting — 2 / 2.5 rather than 2.0 / 2.5."""
    return f"{value:g}"


def extract_goals(data: Any) -> List[Any]:
    """Unwrap goals from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def load(sources: List[str]) -> List[Dict[str, Any]]:
    """Read every page and return goals deduplicated by id (first wins).

    Later pages for the same goal carry newer values; the dedupe keys on id
    so a goal appears once in every KPI.
    """
    seen = {}
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_goals(raw):
            if not isinstance(item, dict):
                continue
            gid = one_line(item.get("id") or item.get("goal_id"))
            if gid and gid not in seen:
                seen[gid] = item
    return list(seen.values())


def progress(item: Dict[str, Any]) -> Optional[float]:
    """Progress ratio toward target; None for qualitative/no-target goals."""
    cur, target = number(item.get("current_value")), number(item.get("target_value"))
    if cur is None or target is None or target == 0:
        return None
    return cur / target


def status(item: Dict[str, Any]) -> str:
    """Status indicator: ✅ achieved / 🟢 on-track active / ⏸ inactive."""
    p = progress(item)
    if p is not None and p >= 1.0:
        return "✅"
    return "🟢" if item.get("is_active", True) else "⏸"


def kpis(goals: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(goals)
    active = sum(1 for g in goals if g.get("is_active", True))
    achieved = sum(1 for g in goals if (p := progress(g)) is not None and p >= 1.0)
    ratios = [p for p in (progress(g) for g in goals) if p is not None]
    avg = 100 * sum(ratios) / len(ratios) if ratios else None
    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "achieved": achieved,
        "avg_progress": avg,
    }


def type_breakdown(goals: List[Dict[str, Any]]) -> List[tuple]:
    """Rows of (goal_type, count, avg_progress%) sorted by count desc."""
    by_type = defaultdict(list)
    for g in goals:
        by_type[one_line(g.get("goal_type")) or "qualitative"].append(g)
    rows = []
    for gtype, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        ratios = [p for p in (progress(i) for i in items) if p is not None]
        avg = f"{100 * sum(ratios) / len(ratios):.0f}%" if ratios else "—"
        rows.append((gtype, len(items), avg))
    return rows


def digest(sources: List[str]) -> str:
    goals = load(sources)
    k = kpis(goals)
    avg = f"{k['avg_progress']:.0f}%" if k["avg_progress"] is not None else "—"
    lines = [
        "# Goals digest",
        "",
        f"- **Total goals:** {k['total']}",
        f"- **Active:** {k['active']}",
        f"- **Inactive:** {k['inactive']}",
        f"- **Achieved (≥100%):** {k['achieved']}",
        f"- **Average progress:** {avg}",
        "",
        "## By type",
        "",
        "| Goal type | Count | Avg progress |",
        "|---|---|---|",
    ]
    for gtype, count, avg in type_breakdown(goals):
        lines.append(f"| {gtype} | {count} | {avg} |")
    lines += ["", "## Goals", ""]
    for g in goals:
        title = one_line(g.get("title") or g.get("description")) or "(no title)"
        cur, target = number(g.get("current_value")), number(g.get("target_value"))
        metric = ""
        if cur is not None and target is not None:
            metric = f" — {fmt_num(cur)}/{fmt_num(target)}"
            if g.get("unit"):
                metric += f" {one_line(g['unit'])}"
        lines.append(f"- {status(g)} **{title}**{metric}")
    return "\n".join(lines) + "\n"


def convert(sources: List[str], destination: str) -> None:
    """Render the digest and write it atomically (exclusive create)."""
    text = digest(sources)
    output_path = Path(destination)
    if ".." in output_path.parts:
        raise ValueError(f"Refusing '..' in output path {output_path}")
    try:
        fd = output_path.open("x", encoding="utf-8")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with fd:
            fd.write(strip_surrogates(text))
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build a Markdown digest from Omi goal exports.")
    ap.add_argument("inputs", nargs="+", help="One or more JSON export files")
    ap.add_argument("-o", "--output", required=True, help="Output Markdown path (exclusive create)")
    args = ap.parse_args(argv)
    try:
        convert(args.inputs, args.output)
    except (ValueError, OSError, json.JSONDecodeError, FileExistsError) as e:
        print(f"goals_digest: {e}", file=sys.stderr)
        return 2
    print(f"goals_digest: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
