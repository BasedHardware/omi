#!/usr/bin/env python3
"""
Convert an Omi goal JSON export to CSV for spreadsheets, pandas, and bulk
imports — the goal-domain counterpart to the conversations CSV recipe.

Usage:
  omi --json goal list --include-inactive --limit 100 | python goals_to_csv.py -o goals.csv
  python goals_to_csv.py goals.json --type numeric --status active -o goals.csv

Fixed columns: id, title, goal_type, current_value, target_value,
unit, progress_pct, is_active, created_at. ``progress_pct`` is the completion
percentage toward target; timestamps normalize to ISO-8601 UTC. Output
defaults to stdout; ``-o`` writes exclusively (never overwrites).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "unit",
    "progress_pct",
    "is_active",
    "created_at",
)
ENVELOPE_KEYS = ("goals", "items", "data")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    value = strip_surrogates(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def number(value: Any) -> Optional[float]:
    """Loose numeric coercion; non-numeric → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_num(value: Optional[float]) -> str:
    """Compact number cell — 2 / 2.5 / blank for None."""
    return f"{value:g}" if value is not None else ""


def _metric(item: Dict[str, Any], key: str) -> Any:
    """GoalResponse nests the categorical + metric under "metric"
    ({type,current,target,unit}) — read it with a flat-key fallback for
    exports that already flattened the shape."""
    metric = item.get("metric")
    if isinstance(metric, dict) and metric.get(key) is not None:
        return metric.get(key)
    flat = item.get(f"{key}_value" if key in ("current", "target") else key)
    if flat is not None:
        return flat
    return item.get("goal_type") if key == "type" else None


def progress_pct(item: Dict[str, Any]) -> str:
    """Completion percentage toward target; blank for qualitative/no-target."""
    cur, target = number(_metric(item, "current")), number(_metric(item, "target"))
    if cur is None or target is None or target == 0:
        return ""
    return f"{100 * cur / target:.1f}"


def iso_utc(value: Any) -> str:
    """Normalize a timestamp to ISO-8601 UTC (``...Z``); unparseable → raw."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, AttributeError, OverflowError):
        return s


def normalize_row(item: Any) -> Optional[List[str]]:
    """Project a raw goal dict onto the fixed column set."""
    if not isinstance(item, dict):
        return None
    return [
        spreadsheet_text(item.get("id") or item.get("goal_id")),
        spreadsheet_text(item.get("title") or item.get("description")),
        spreadsheet_text(_metric(item, "type") or item.get("goal_type")),
        fmt_num(number(_metric(item, "current"))),
        fmt_num(number(_metric(item, "target"))),
        spreadsheet_text(_metric(item, "unit")),
        progress_pct(item),
        "1" if item.get("is_active", True) else "0",
        iso_utc(item.get("created_at")),
    ]


def unwrap(payload: Any) -> List[Any]:
    """Extract the goal list from a CLI export envelope."""
    if isinstance(payload, dict):
        if "error" in payload:
            return []
        for key in ENVELOPE_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def parse_filter(spec: Optional[str]) -> Optional[set]:
    """Parse a comma-separated filter spec; empty → no filtering."""
    if not spec:
        return None
    vals = {v.strip().lower() for v in spec.split(",") if v.strip()}
    return vals or None


def convert(payload: Any, types: Optional[set], statuses: Optional[set]) -> List[List[str]]:
    """Normalize every goal row, applying optional --type/--status filters."""
    rows = []
    for raw in unwrap(payload):
        if not isinstance(raw, dict):
            continue
        gtype = str(_metric(raw, "type") or raw.get("goal_type") or "qualitative").strip().lower()
        status = "active" if raw.get("is_active", True) else "inactive"
        if types is not None and gtype not in types:
            continue
        if statuses is not None and status not in statuses:
            continue
        row = normalize_row(raw)
        if row is not None:
            rows.append(row)
    return rows


def emit_csv(rows: List[List[str]]) -> bytes:
    """Render rows as UTF-8-BOM CSV bytes (Excel/Sheets open it natively)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(FIELDS)
    w.writerows(rows)
    return b'\xef\xbb\xbf' + buf.getvalue().encode("utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert an Omi goal JSON export to CSV.")
    ap.add_argument("input", nargs="?", default="-", help="Input JSON file (default: stdin)")
    ap.add_argument("-o", "--output", help="Write CSV to this path (exclusive create; stdout if omitted)")
    ap.add_argument("--type", help="Comma-separated goal_type filter (e.g. numeric,scale)")
    ap.add_argument("--status", help="Comma-separated status filter (active,inactive)")
    args = ap.parse_args(argv)

    try:
        raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
    except OSError as e:
        print(f"goals_to_csv: cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"goals_to_csv: invalid JSON input: {e}", file=sys.stderr)
        return 2

    rows = convert(payload, parse_filter(args.type), parse_filter(args.status))
    blob = emit_csv(rows)

    if not args.output:
        sys.stdout.buffer.write(blob)
        return 0
    out_path = Path(args.output)
    try:
        fd = out_path.open("xb")
    except FileExistsError:
        print(f"goals_to_csv: refusing to overwrite existing file: {out_path}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"goals_to_csv: cannot create output: {e}", file=sys.stderr)
        return 2
    try:
        with fd:
            fd.write(blob)
    except OSError as e:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"goals_to_csv: write failed: {e}", file=sys.stderr)
        return 2
    print(f"goals_to_csv: wrote {len(rows)} row(s) to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
