"""Convert Omi conversations JSON exports into an iCalendar (.ics) calendar file (RFC 5545).

Usage:
    # Print iCalendar feed to stdout from saved export
    python conversations_to_ics.py conversations.json

    # Write events to standalone .ics file
    python conversations_to_ics.py conversations.json -o conversations.ics

    # Filter by category with custom default session length
    python conversations_to_ics.py conversations.json --category work --default-length 45 -o work.ics

    # Stream from omi CLI pipeline
    omi --json conversation list --limit 200 | python conversations_to_ics.py - -o conversations.ics
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

DEFAULT_CALNAME = "Omi Conversations"
DEFAULT_LENGTH_MINS = 30
PRODID = "-//omi-cli examples//conversations_to_ics//EN"


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


def unwrap_conversations(raw: Any, source_label: str) -> List[Any]:
    """Extract conversations list from various JSON envelopes or return bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("conversations", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if any(k in raw for k in ("id", "started_at", "structured")):
            return [raw]
        return []
    raise ValueError(f"{source_label}: expected JSON array or object containing conversations")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate conversations from files or stdin."""
    conversations_by_id: Dict[str, Dict[str, Any]] = {}
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
        items = unwrap_conversations(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each conversation must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in conversations_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            conversations_by_id[clean_id] = item
    return conversations_by_id


def build_ics(
    conversations_by_id: Dict[str, Dict[str, Any]],
    category_filter: Optional[str] = None,
    default_length_mins: int = DEFAULT_LENGTH_MINS,
    calendar_name: str = DEFAULT_CALNAME,
) -> Tuple[str, int, int]:
    """Build RFC 5545 iCalendar payload from conversations."""
    default_length = timedelta(minutes=max(1, default_length_mins))
    now = stamp(datetime.now(timezone.utc))
    clean_calname = ics_text(calendar_name) or DEFAULT_CALNAME
    cat_match = category_filter.strip().lower() if category_filter else None

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

    sorted_items = sorted(
        conversations_by_id.values(),
        key=lambda it: (
            parse_time(it.get("started_at")) or datetime.max.replace(tzinfo=timezone.utc),
            str(it.get("id") or ""),
        ),
    )

    for item in sorted_items:
        structured = item.get("structured")
        if not isinstance(structured, dict):
            structured = {}

        category = structured.get("category") or item.get("category")
        clean_cat = str(category).strip().lower() if category else ""
        if cat_match and clean_cat != cat_match:
            continue

        start = parse_time(item.get("started_at"))
        if start is None:
            skipped_count += 1
            continue

        end = parse_time(item.get("finished_at"))
        if end is None or end <= start:
            end = start + default_length

        item_id = ics_text(item.get("id")) or "unknown"
        title = ics_text(structured.get("title") or item.get("title")) or "(untitled conversation)"
        notes = [f"Omi conversation: {item_id}"]

        if category:
            notes.append(f"Category: {ics_text(category)}")
        folder = item.get("folder_name") or item.get("folder")
        if folder:
            notes.append(f"Folder: {ics_text(folder)}")
        if item.get("source"):
            notes.append(f"Source: {ics_text(item.get('source'))}")

        categories_val = f"Omi,{ics_text(category)}" if category else "Omi"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:omi-conversation-{item_id}@omi-cli",
            f"DTSTAMP:{now}",
            f"DTSTART:{stamp(start)}",
            f"DTEND:{stamp(end)}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{'\\n'.join(notes)}",
            "STATUS:CONFIRMED",
            f"CATEGORIES:{categories_val}",
            "END:VEVENT",
        ])
        events_count += 1

    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(line)]
    return "\r\n".join(folded) + "\r\n", events_count, skipped_count


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    category_filter: Optional[str] = None,
    default_length_mins: int = DEFAULT_LENGTH_MINS,
    calendar_name: str = DEFAULT_CALNAME,
    overwrite: bool = False,
) -> Tuple[int, int]:
    """Load conversations, build iCalendar file, and write to destination file or stdout."""
    items = load(sources)
    payload_str, events_count, skipped_count = build_ics(
        items,
        category_filter=category_filter,
        default_length_mins=default_length_mins,
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
        tmp_name = f".tmp_conversations_ics_{uuid.uuid4().hex}.ics"
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
        description="Convert Omi conversations JSON exports into an iCalendar (.ics) calendar file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more conversation JSON export files, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", help="Destination ICS file path (defaults to stdout)")
    parser.add_argument(
        "--category",
        help="Filter conversations by category (case-insensitive)",
    )
    parser.add_argument(
        "--default-length",
        type=int,
        default=DEFAULT_LENGTH_MINS,
        help=f"Default duration in minutes when finished_at is missing (default: {DEFAULT_LENGTH_MINS})",
    )
    parser.add_argument(
        "--calendar-name",
        default=DEFAULT_CALNAME,
        help=f"Calendar display name for X-WR-CALNAME (default: '{DEFAULT_CALNAME}')",
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
            category_filter=args.category,
            default_length_mins=args.default_length,
            calendar_name=args.calendar_name,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"iCalendar written to {args.output} ({written} events written, {skipped} items without start time)")
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
