#!/usr/bin/env python3
"""Convert Omi goals and habit progress JSON exports into JSON Lines (JSONL / NDJSON) format.

Usage:
    python goals_to_jsonl.py goals.json -o goals.jsonl
    omi --json goal list | python goals_to_jsonl.py - -o dataset.jsonl
    python goals_to_jsonl.py page1.json page2.json -o all_goals.jsonl --status active

Outputs newline-delimited JSON (JSONL) optimized for habit analytics, Pandas,
DuckDB, and automated goal-tracking dashboards.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def utc_stamp(value: Optional[str]) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return value


def parse_boolean(value: Any) -> bool:
    """Normalize completion status to a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def parse_float(value: Any, default: float = 0.0) -> float:
    """Safely parse float numbers."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of goal dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("goals", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped goals object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each goal must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: goal missing required 'id' field")
        results.append(item)

    return results


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a standardized dictionary for JSONL streaming."""
    title = str(item.get("title") or item.get("name") or "").strip()
    desc = str(item.get("description") or "").strip()
    unit = str(item.get("unit") or "").strip() or None
    target_val = parse_float(item.get("target_value"), 1.0)
    current_val = parse_float(item.get("current_value"), 0.0)

    if target_val > 0:
        progress_pct = round((current_val / target_val) * 100.0, 1)
    else:
        progress_pct = 100.0 if current_val > 0 else 0.0

    completed = parse_boolean(item.get("completed")) or (progress_pct >= 100.0)

    record: Dict[str, Any] = {
        "id": str(item.get("id")),
        "title": title,
        "description": desc,
        "target_value": target_val,
        "current_value": current_val,
        "unit": unit,
        "progress_pct": progress_pct,
        "completed": completed,
        "target_date": utc_stamp(item.get("target_date")),
        "created_at": utc_stamp(item.get("created_at")),
        "updated_at": utc_stamp(item.get("updated_at")),
    }

    return record


def convert_paths_to_jsonl(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    status_filter: Optional[str] = "all",
) -> int:
    """Convert goal JSON exports into JSONL format with optional deduplication and status filtering."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_goals(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_goals(content, str(p)))

    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for item in all_items:
        gid = str(item.get("id"))
        if gid not in seen_ids:
            seen_ids.add(gid)
            norm = normalize_record(item)
            if status_filter == "active" and norm["completed"]:
                continue
            if status_filter == "completed" and not norm["completed"]:
                continue
            deduped.append(norm)

    lines = [json.dumps(g, ensure_ascii=False) for g in deduped]
    output_text = "\n".join(lines) + ("\n" if lines else "")

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)

    return len(deduped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports into JSON Lines (JSONL / NDJSON) format."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSONL file (defaults to stdout)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "active", "completed"],
        default="all",
        help="Filter goals by status (default: all)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_jsonl(args.inputs, args.output, status_filter=args.status)
        if args.output != "-":
            print(f"Exported {count} goal(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
