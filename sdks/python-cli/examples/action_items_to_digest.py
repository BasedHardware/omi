"""Generate a concise Markdown digest of Omi action items, completion rates, and deadlines.

Usage:
    # Print digest to stdout from saved export
    python action_items_to_digest.py tasks.json

    # Write digest to file with local timezone offset
    python action_items_to_digest.py tasks.json -o digest.md --utc-offset +09:00

    # Pipeline stream from omi CLI
    omi --json action-item list --limit 200 | python action_items_to_digest.py - -o digest.md
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

DONE_WORDS = {"true", "yes", "1", "done", "completed", "x"}


def is_completed(value: Any) -> bool:
    """Normalize completion state handling booleans, numbers, and strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


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


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta with strict boundary checking (-14:00 to +14:00)."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    hours = int(value[1:3])
    minutes = int(value[4:])
    if minutes > 59 or hours > 14 or (hours == 14 and minutes > 0):
        raise ValueError(f"UTC offset {value!r} out of valid range (-14:00 to +14:00)")
    delta = timedelta(hours=hours, minutes=minutes)
    return -delta if value[0] == "-" else delta


def clean_markdown_cell(value: Any) -> str:
    """Sanitize arbitrary user strings for safe Markdown table and list rendering."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("|", "\\|")
    return " ".join(text.split())


def unwrap_items(raw: Any, source_label: str) -> List[Any]:
    """Extract action items from various JSON envelopes or return the bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_items", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        return [raw]
    raise ValueError(f"{source_label}: expected JSON array or object containing action items")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate action items from files or stdin."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
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
        items = unwrap_items(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each action item must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def build_digest(
    items_by_id: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    offset_label: str = "",
    status_filter: str = "all",
    now: Optional[datetime] = None,
) -> str:
    """Generate Markdown digest with completion analytics, overdue warnings, and upcoming deadlines."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    filter_mode = status_filter.strip().lower() if status_filter else "all"

    # Filter items
    active_items: List[Tuple[str, Dict[str, Any]]] = []
    for item_id, item in items_by_id.items():
        completed = is_completed(item.get("completed", False))
        if filter_mode == "open" and completed:
            continue
        if filter_mode == "completed" and not completed:
            continue
        active_items.append((item_id, item))

    total = len(active_items)
    if total == 0:
        return "# Omi Action Items Digest\n\n_No action items found matching the export criteria._\n"

    completed_count = sum(1 for _, it in active_items if is_completed(it.get("completed", False)))
    open_count = total - completed_count
    rate = (completed_count / total * 100.0) if total > 0 else 0.0

    overdue: List[Tuple[datetime, str, str]] = []
    upcoming: List[Tuple[datetime, str, str]] = []
    undated_count = 0
    per_day: Dict[str, List[int]] = defaultdict(lambda: [0, 0])  # day -> [open, completed]

    now_local = now + offset
    upcoming_limit = now + timedelta(days=7)

    for item_id, item in active_items:
        done = is_completed(item.get("completed", False))
        due_dt = parse_time(item.get("due_at"))
        desc = clean_markdown_cell(item.get("description") or "Untitled task")

        if due_dt is None:
            undated_count += 1
        else:
            due_local = due_dt + offset
            day_str = due_local.strftime("%Y-%m-%d")
            if done:
                per_day[day_str][1] += 1
            else:
                per_day[day_str][0] += 1
                if due_dt < now:
                    overdue.append((due_dt, desc, item_id))
                elif due_dt <= upcoming_limit:
                    upcoming.append((due_dt, desc, item_id))

    overdue.sort(key=lambda x: (x[0], x[2]))
    upcoming.sort(key=lambda x: (x[0], x[2]))

    lines: List[str] = [
        "# Omi Action Items Digest",
        "",
        (
            f"**Total Tasks:** {total} · **Completed:** {completed_count} ({rate:.1f}%) · "
            f"**Open:** {open_count} · **Overdue:** {len(overdue)}"
        ),
        "",
        "## Summary",
        "",
        "| Metric | Count | Ratio |",
        "|---|---:|---:|",
        f"| Completed | {completed_count} | {rate:.1f}% |",
        f"| Open | {open_count} | {(open_count / total * 100.0):.1f}% |",
        f"| Overdue (Open) | {len(overdue)} | {(len(overdue) / total * 100.0):.1f}% |",
        f"| Due Within 7 Days | {len(upcoming)} | {(len(upcoming) / total * 100.0):.1f}% |",
        f"| Undated | {undated_count} | {(undated_count / total * 100.0):.1f}% |",
    ]

    if overdue:
        lines += [
            "",
            "## ⚠️ Overdue Tasks",
            "",
            "These open action items have passed their specified due date:",
            "",
        ]
        for due_dt, desc, item_id in overdue:
            due_local = due_dt + offset
            days_ago = max(1, (now - due_dt).days)
            day_word = "day" if days_ago == 1 else "days"
            lines.append(
                f"- **{desc}** · Due: {due_local.strftime('%Y-%m-%d')} "
                f"(_overdue by {days_ago} {day_word}_) · `{item_id}`"
            )

    if upcoming:
        lines += [
            "",
            "## 📅 Upcoming Deadlines (Next 7 Days)",
            "",
            "Action items scheduled for completion within the coming week:",
            "",
        ]
        for due_dt, desc, item_id in upcoming:
            due_local = due_dt + offset
            lines.append(
                f"- **{desc}** · Due: {due_local.strftime('%Y-%m-%d (%a)')} · `{item_id}`"
            )

    if per_day:
        lines += [
            "",
            "## Due Date Schedule",
            "",
            "| Date | Open | Completed | Total |",
            "|---|---:|---:|---:|",
        ]
        for day_str in sorted(per_day.keys()):
            open_n, done_n = per_day[day_str]
            lines.append(f"| {day_str} | {open_n} | {done_n} | {open_n + done_n} |")

    time_note = f" at {offset_label}" if offset_label else " in UTC"
    lines += ["", f"_Digest generated based on reference time {now_local.strftime('%Y-%m-%d %H:%M:%S')}{time_note}._\n"]
    return "\n".join(lines)


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    offset: timedelta = timedelta(0),
    offset_label: str = "",
    status_filter: str = "all",
    overwrite: bool = False,
    now: Optional[datetime] = None,
) -> int:
    """Load items from sources, build Markdown digest, and write to destination or stdout."""
    items = load(sources)
    digest_text = build_digest(
        items,
        offset=offset,
        offset_label=offset_label,
        status_filter=status_filter,
        now=now,
    )
    payload = digest_text.encode("utf-8")

    status_norm = status_filter.strip().lower() if status_filter else "all"
    row_count = sum(
        1
        for item in items.values()
        if (
            status_norm == "all"
            or (status_norm == "open" and not is_completed(item.get("completed", False)))
            or (status_norm == "completed" and is_completed(item.get("completed", False)))
        )
    )

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
        # Atomic write to temporary file in same directory with default permissions, then replace destination
        tmp_name = f".tmp_tasks_digest_{uuid.uuid4().hex}.md"
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
        description="Convert Omi action items JSON exports into a Markdown digest."
    )
    parser.add_argument("inputs", nargs="+", help="One or more action items JSON export files, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Destination Markdown file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by completion status (default: all)",
    )
    parser.add_argument(
        "--utc-offset",
        default="",
        help="Local UTC offset, e.g. +09:00 or --utc-offset=-05:00",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    offset = timedelta(0)
    offset_label = ""
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
            offset_label = args.utc_offset
        except ValueError as exc:
            sys.exit(f"Digest failed: {exc}")

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            offset=offset,
            offset_label=offset_label,
            status_filter=args.status,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"Digest written to {args.output} ({count} action items)")
        return 0
    except (OSError, ValueError) as exc:
        sys.exit(f"Digest failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
