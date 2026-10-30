"""Convert Omi action items JSON exports into an iCalendar (.ics) calendar file (RFC 5545).

Usage:
    # Print iCalendar feed to stdout from saved export
    python action_items_to_ics.py action_items.json

    # Write events to standalone .ics file
    python action_items_to_ics.py action_items.json -o tasks.ics

    # Filter to open pending tasks with 60-minute duration
    python action_items_to_ics.py action_items.json --status open --event-length 60 -o pending.ics

    # Stream from omi CLI pipeline
    omi --json action-item list --limit 200 | python action_items_to_ics.py - -o tasks.ics
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

DEFAULT_CALNAME = "Omi Action Items"
PRODID = "-//omi-cli examples//action_items_to_ics//EN"
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


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Drop C0 control codes (except newline/tab), surrogates, and noncharacters
    clean = "".join(
        ch for ch in value
        if (ch >= " " or ch in "\n\t") and not ("\ud800" <= ch <= "\udfff") and ch not in ("\ufffe", "\uffff")
    )
    return (
        clean.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


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


def stamp(dt: datetime) -> str:
    """Format UTC datetime into an iCalendar timestamp string."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> List[str]:
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts: List[str] = []
    chunk: bytes = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk = b" " + b
            limit = 75
        else:
            chunk += b
    if chunk:
        parts.append(chunk.decode("utf-8"))
    return parts


def unwrap_items(raw: Any, source_label: str) -> List[Any]:
    """Extract action items from various JSON envelopes or return bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_items", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if any(k in raw for k in ("description", "completed", "due_at", "created_at")):
            return [raw]
        return []
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
            sanitized_id = ics_text(item_id).strip()
            if sanitized_id:
                clean_id = sanitized_id
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            item["id"] = clean_id
            items_by_id[clean_id] = item
    return items_by_id


def build_ics(
    items_by_id: Dict[str, Dict[str, Any]],
    status_filter: str = "all",
    event_length_mins: int = 30,
    calendar_name: str = DEFAULT_CALNAME,
) -> Tuple[str, int, int]:
    """Build RFC 5545 iCalendar payload from action items."""
    norm_status = status_filter.strip().lower() if status_filter else "all"
    event_length = timedelta(minutes=max(1, event_length_mins))
    now = stamp(datetime.now(timezone.utc))
    clean_calname = ics_text(calendar_name) or DEFAULT_CALNAME

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{clean_calname}",
    ]

    events_count = 0
    skipped_count = 0

    # Sort items deterministically by due date, created date, and ID
    sorted_items = sorted(
        items_by_id.values(),
        key=lambda it: (
            parse_time(it.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc),
            parse_time(it.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(it.get("id") or ""),
        ),
    )

    for item in sorted_items:
        completed = is_completed(item.get("completed", False))
        if norm_status == "open" and completed:
            continue
        if norm_status == "completed" and not completed:
            continue

        due = parse_time(item.get("due_at"))
        if due is None:
            skipped_count += 1
            continue

        item_id = ics_text(item.get("id")) or "unknown"
        desc = ics_text(item.get("description")) or "(no description)"
        if completed:
            desc = f"[Completed] {desc}"

        notes = [f"Omi action item: {item_id}"]
        conv_id = item.get("conversation_id")
        if conv_id and str(conv_id).strip():
            notes.append(f"Conversation: {ics_text(str(conv_id).strip())}")
        if completed:
            notes.append("Status: Completed")
        else:
            notes.append("Status: Needs Action")

        created = parse_time(item.get("created_at"))
        desc_notes = "\\n".join(notes)

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:omi-action-{item_id}@omi-cli",
            f"DTSTAMP:{now}",
            f"DTSTART:{stamp(due)}",
            f"DTEND:{stamp(due + event_length)}",
            f"SUMMARY:{desc}",
            f"DESCRIPTION:{desc_notes}",
            "STATUS:CONFIRMED",
            "CATEGORIES:Omi",
        ])
        if created is not None:
            lines.append(f"CREATED:{stamp(created)}")
        lines.append("END:VEVENT")
        events_count += 1

    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(line)]
    return "\r\n".join(folded) + "\r\n", events_count, skipped_count


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    status_filter: str = "all",
    event_length_mins: int = 30,
    calendar_name: str = DEFAULT_CALNAME,
    overwrite: bool = False,
) -> Tuple[int, int]:
    """Load action items, build iCalendar file, and write to destination file or stdout."""
    items = load(sources)
    payload_str, events_count, skipped_count = build_ics(
        items,
        status_filter=status_filter,
        event_length_mins=event_length_mins,
        calendar_name=calendar_name,
    )
    payload = payload_str.encode("utf-8")

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return events_count, skipped_count

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
            os.chmod(output_path, 0o644)
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_action_items_ics_{uuid.uuid4().hex}.ics"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                os.chmod(tmp_path, 0o644)
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.chmod(tmp_path, 0o644)
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return events_count, skipped_count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into an iCalendar (.ics) calendar file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more action items JSON export files, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", help="Destination ICS file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by status (default: all)",
    )
    parser.add_argument(
        "--event-length",
        type=int,
        default=30,
        help="Event duration in minutes for scheduled tasks (default: 30)",
    )
    parser.add_argument(
        "--calendar-name",
        default=DEFAULT_CALNAME,
        help=f"Calendar name for X-WR-CALNAME (default: '{DEFAULT_CALNAME}')",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing destination file",
    )

    args = parser.parse_args(argv)

    try:
        written, skipped = convert(
            args.inputs,
            destination=args.output,
            status_filter=args.status,
            event_length_mins=args.event_length,
            calendar_name=args.calendar_name,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"iCalendar written to {args.output} ({written} events written, {skipped} items without due date)")
        elif skipped > 0:
            print(f"Note: skipped {skipped} item(s) without due date", file=sys.stderr)
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"iCalendar export failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
