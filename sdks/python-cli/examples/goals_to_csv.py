"""Convert Omi goals and milestone progress into a spreadsheet-safe CSV file.

Usage:
    # Print CSV to stdout from saved export
    python goals_to_csv.py goals.json

    # Write CSV to file for Excel or Google Sheets
    python goals_to_csv.py goals.json -o goals.csv

    # Add UTF-8 BOM for Microsoft Excel on Windows
    python goals_to_csv.py goals.json -o goals.csv --excel-bom

    # Filter to active goals only
    python goals_to_csv.py goals.json --status active -o active_goals.csv

    # Pipeline stream directly from omi CLI
    omi --json goal list --limit 100 --include-inactive | python goals_to_csv.py - -o goals.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence
import uuid

COLUMNS = (
    "id",
    "title",
    "goal_type",
    "status",
    "current_value",
    "target_value",
    "unit",
    "progress_pct",
    "is_active",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value: Any) -> str:
    """Render a field as spreadsheet-safe text, neutralizing formula injection.

    Leading characters '=', '+', '-', '@', '\t', '\r', '\n' are escaped with a
    leading apostrophe so spreadsheet engines (Excel, Calc, Sheets) treat them as
    plain strings rather than executable formulas or macro invocations.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    if clean.lstrip().startswith(("=", "+", "-", "@")) or clean.startswith(("\t", "\r", "\n")):
        return "'" + clean
    return clean


def parse_float(value: Any) -> Optional[float]:
    """Parse a numeric value into a finite float, or None if missing or non-finite."""
    if value is None:
        return None
    try:
        val = float(value)
        return val if math.isfinite(val) else None
    except (ValueError, TypeError):
        return None


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except (ValueError, OverflowError):
        return None


def iso_utc(dt: Optional[datetime]) -> str:
    """Format an aware UTC datetime as ISO-8601 UTC string."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def calculate_progress(goal: Dict[str, Any]) -> Optional[float]:
    """Calculate progress percentage (0.0 to 100.0+) based on goal type and values."""
    goal_type = str(goal.get("goal_type") or "").strip().lower()
    current = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_val = parse_float(goal.get("min_value"))
    max_val = parse_float(goal.get("max_value"))

    if goal_type == "boolean":
        if current is not None:
            return 100.0 if current >= 1.0 else 0.0
        return 100.0 if not goal.get("is_active", True) else 0.0

    if goal_type == "scale":
        if current is not None and min_val is not None and max_val is not None and max_val > min_val:
            span = max_val - min_val
            pct = ((current - min_val) / span) * 100.0
            return round(max(0.0, pct), 1)
        if current is not None and target is not None and target > 0:
            return round(max(0.0, (current / target) * 100.0), 1)

    if current is not None and target is not None and target > 0:
        return round(max(0.0, (current / target) * 100.0), 1)

    return None


def unwrap_goals(raw: Any, source_label: str) -> List[Any]:
    """Extract goal objects from various JSON envelopes or return bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("goals", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if any(k in raw for k in ("title", "goal_type", "target_value", "is_active")):
            return [raw]
        return []
    raise ValueError(f"{source_label}: expected JSON array or object containing goals")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate goals from files or stdin by ID."""
    goals_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            content = sys.stdin.buffer.read()
            source_label = "stdin"
        else:
            source_label = source
            content = Path(source).read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_goals(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each goal must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in goals_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            goals_by_id[clean_id] = item
    return goals_by_id


def build_rows(
    goals_by_id: Dict[str, Dict[str, Any]],
    status_filter: str = "all",
    type_filter: str = "all",
) -> List[Dict[str, Any]]:
    """Filter and build sanitized spreadsheet rows from goal records."""
    norm_status = status_filter.strip().lower() if status_filter else "all"
    norm_type = type_filter.strip().lower() if type_filter else "all"

    rows: List[Dict[str, Any]] = []
    for item_id, item in goals_by_id.items():
        is_active = bool(item.get("is_active", True))
        goal_type = str(item.get("goal_type") or "qualitative").strip().lower()
        progress = calculate_progress(item)
        is_achieved = (progress is not None and progress >= 100.0) or (not is_active)

        if is_achieved:
            status = "completed"
        elif is_active:
            status = "active"
        else:
            status = "inactive"

        if norm_status == "active" and status != "active":
            continue
        if norm_status == "completed" and status != "completed":
            continue
        if norm_status == "inactive" and status != "inactive":
            continue

        if norm_type != "all" and goal_type != norm_type:
            continue

        created_dt = parse_time(item.get("created_at"))
        updated_dt = parse_time(item.get("updated_at")) or created_dt

        curr = parse_float(item.get("current_value"))
        targ = parse_float(item.get("target_value"))

        rows.append({
            "id": spreadsheet_text(item_id),
            "title": spreadsheet_text(item.get("title") or "Untitled goal"),
            "goal_type": spreadsheet_text(goal_type),
            "status": status,
            "current_value": "" if curr is None else str(curr),
            "target_value": "" if targ is None else str(targ),
            "unit": spreadsheet_text(item.get("unit") or ""),
            "progress_pct": "" if progress is None else f"{progress:.1f}",
            "is_active": "true" if is_active else "false",
            "created_at": iso_utc(created_dt),
            "updated_at": iso_utc(updated_dt),
            "_sort_key": (created_dt or datetime.min.replace(tzinfo=timezone.utc), item_id),
        })

    rows.sort(key=lambda r: r["_sort_key"], reverse=True)
    for r in rows:
        r.pop("_sort_key", None)
    return rows


def build_csv_payload(rows: List[Dict[str, Any]], excel_bom: bool = False) -> bytes:
    """Serialize rows into CSV format with optional Excel UTF-8 BOM."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    encoded = buf.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if excel_bom else encoded


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    status_filter: str = "all",
    type_filter: str = "all",
    excel_bom: bool = False,
    overwrite: bool = False,
) -> int:
    """Load goals from sources, build spreadsheet-safe CSV, and write to destination or stdout."""
    goals_by_id = load(sources)
    rows = build_rows(goals_by_id, status_filter=status_filter, type_filter=type_filter)
    payload = build_csv_payload(rows, excel_bom=excel_bom)
    row_count = len(rows)

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return row_count

    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --overwrite to replace)"
            ) from None
        try:
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_goals_csv_{uuid.uuid4().hex}.csv"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return row_count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports into a spreadsheet-safe CSV file."
    )
    parser.add_argument("inputs", nargs="+", help="One or more goals JSON export files, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Destination CSV file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "active", "completed", "inactive"],
        default="all",
        help="Filter goals by status (default: all)",
    )
    parser.add_argument(
        "--type",
        choices=["all", "numeric", "scale", "boolean", "qualitative"],
        default="all",
        help="Filter goals by goal type (default: all)",
    )
    parser.add_argument(
        "--excel-bom",
        action="store_true",
        help="Include UTF-8 Byte Order Mark for Excel on Windows",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            status_filter=args.status,
            type_filter=args.type,
            excel_bom=args.excel_bom,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"Goals CSV written to {args.output} ({count} goals)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"Goals CSV export failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
