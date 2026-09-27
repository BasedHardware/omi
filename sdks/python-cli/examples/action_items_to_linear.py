"""Convert Omi action-item JSON exports to Linear CSV format for issue import.

See action_items_linear.md for the full recipe and Linear import instructions.

Usage:
    omi --json action-item list --limit 200 > action_items.json
    python action_items_to_linear.py linear_issues.csv action_items.json
    python action_items_to_linear.py --status pending --priority High linear_urgent.csv action_items.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DONE_WORDS = {"true", "yes", "1", "done", "completed"}


def clean_text(value: Any) -> str:
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    else:
        text = value
    return " ".join(text.split())


def is_done(value: Any) -> bool:
    """Normalize completed status into a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local timezone display."""
    if not isinstance(value, str):
        raise ValueError("UTC offset must be a string")
    value = value.strip()
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    hours = int(value[1:3])
    minutes = int(value[4:])
    if minutes > 59 or hours > 14:
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    delta = timedelta(hours=hours, minutes=minutes)
    if delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load_action_items(sources: Sequence[str]) -> List[Dict[str, Any]]:
    """Load and deduplicate action items from multiple JSON sources or envelopes."""
    items_map: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for source in sources:
        path = Path(source)
        content = path.read_bytes().decode("utf-8-sig")
        payload = json.loads(content)

        if isinstance(payload, dict):
            found_key = None
            for key in ("action_items", "items", "data"):
                if key in payload:
                    found_key = key
                    break
            if found_key is not None:
                items = payload[found_key]
            elif "id" in payload:
                items = [payload]
            else:
                raise ValueError(f"{source}: expected JSON array or object containing action items")
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"{source}: expected JSON array or object containing action items")

        if not isinstance(items, list):
            raise ValueError(f"{source}: action items payload must be a JSON array")

        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each action item must be a JSON object")
            item_id = raw.get("id")
            if item_id is None or str(item_id).strip() == "":
                raise ValueError(f"{source}: action item missing non-empty string 'id'")
            items_map[str(item_id)] = raw

    return list(items_map.values())


def format_linear_row(
    raw: Dict[str, Any],
    offset: timedelta = timedelta(0),
    default_status: str = "Todo",
    default_priority: str = "No priority",
    extra_labels: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """Format single action item into Linear CSV compatible dictionary."""
    title = clean_text(raw.get("description") or raw.get("title")) or "Untitled action item"
    completed = is_done(raw.get("completed"))
    status = "Done" if completed else default_status

    due_dt = parse_time(raw.get("due_at"))
    due_str = (due_dt + offset).strftime("%Y-%m-%d") if due_dt else ""

    created_dt = parse_time(raw.get("created_at"))
    created_str = (created_dt + offset).strftime("%Y-%m-%d %H:%M:%S") if created_dt else ""

    item_id = clean_text(raw.get("id"))
    conv_id = clean_text(raw.get("conversation_id"))

    description_lines = [f"Imported from Omi AI wearable (Item ID: `{item_id}`)."]
    if conv_id:
        description_lines.append(f"Origin Conversation ID: `{conv_id}`.")

    labels = ["omi", "action-item"]
    if extra_labels:
        for lbl in extra_labels:
            cl = clean_text(lbl).replace(" ", "-")
            if cl and cl not in labels:
                labels.append(cl)

    return {
        "Title": title,
        "Description": " ".join(description_lines),
        "Status": status,
        "Priority": default_priority,
        "Due Date": due_str,
        "Labels": " ".join(labels),
        "Created At": created_str,
    }


def convert(
    sources: Sequence[str],
    destination: str,
    offset: timedelta = timedelta(0),
    default_status: str = "Todo",
    default_priority: str = "No priority",
    extra_labels: Optional[Sequence[str]] = None,
    status_filter: Optional[str] = None,
    force: bool = False,
) -> int:
    """Convert action items JSON exports into Linear-compatible CSV."""
    items = load_action_items(sources)

    if status_filter and status_filter.lower() != "all":
        want_completed = (status_filter.lower() == "completed")
        items = [it for it in items if is_done(it.get("completed")) == want_completed]

    output_path = Path(destination)
    if not force:
        try:
            output_file = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --force to overwrite)") from None
    else:
        output_file = output_path.open("wb")

    fieldnames = ["Title", "Description", "Status", "Priority", "Due Date", "Labels", "Created At"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for it in items:
        row = format_linear_row(
            it,
            offset=offset,
            default_status=default_status,
            default_priority=default_priority,
            extra_labels=extra_labels,
        )
        writer.writerow(row)

    payload = buffer.getvalue().encode("utf-8")
    try:
        with output_file:
            output_file.write(payload)
    except OSError:
        if not force:
            output_path.unlink(missing_ok=True)
        raise
    return len(items)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Export Omi action items to Linear CSV issue import format."
    )
    parser.add_argument("destination", help="destination CSV file to create")
    parser.add_argument("sources", nargs="+", help="one or more JSON action item export files")
    parser.add_argument(
        "--utc-offset",
        type=parse_offset,
        default=timedelta(0),
        help="UTC offset for dates, e.g. +09:00 or -05:00 (default: +00:00)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "pending", "completed"],
        default="all",
        help="filter action items by completion status (default: all)",
    )
    parser.add_argument(
        "--priority",
        default="No priority",
        help="default Linear priority (e.g. Urgent, High, Medium, Low, No priority; default: No priority)",
    )
    parser.add_argument(
        "--label",
        action="append",
        dest="labels",
        default=[],
        help="additional label to attach to each Linear issue (repeatable)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite destination file if it already exists",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    try:
        count = convert(
            sources=args.sources,
            destination=args.destination,
            offset=args.utc_offset,
            default_status="Todo",
            default_priority=args.priority,
            extra_labels=args.labels,
            status_filter=args.status,
            force=args.force,
        )
        print(f"Exported {count} action item(s) to Linear CSV: {args.destination}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
