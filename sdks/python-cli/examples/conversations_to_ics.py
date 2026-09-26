#!/usr/bin/env python3
"""Convert Omi conversations JSON exports into an iCalendar (.ics) file.

Usage:
    python conversations_to_ics.py conversations.json -o history.ics
    omi --json conversation list | python conversations_to_ics.py - -o history.ics
    python conversations_to_ics.py page1.json page2.json -o all_history.ics

Generates an RFC 5545 compliant iCalendar (.ics) file mapping conversations to
calendar events for Apple Calendar, Google Calendar, Outlook, and Thunderbird.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_LENGTH = timedelta(minutes=30)
PRODID = "-//Omi//omi-cli conversations_to_ics//EN"


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    Coerces non-null values safely to strings and escapes backslashes, semicolons,
    commas, and newlines to preserve calendar parser integrity.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def stamp(dt: datetime) -> str:
    """Format a datetime into an iCalendar UTC timestamp 'YYYYMMDDTHHMMSSZ'."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> List[str]:
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]

    parts: List[str] = []
    chunk = b""
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


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def conversation_to_event(conv: Dict[str, Any], now_utc: datetime) -> Optional[List[str]]:
    """Convert a single conversation item to an iCalendar VEVENT block, or None if no start time."""
    start = ics_datetime(conv.get("started_at"))
    if not start:
        return None

    end = ics_datetime(conv.get("finished_at"))
    if not end or end <= start:
        end = start + DEFAULT_LENGTH

    conv_id = str(conv.get("id"))
    uid = f"{conv_id}@omi"

    structured: Dict[str, Any] = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or conv.get("title") or "Omi Conversation"
    summary = ics_text(title)

    category = structured.get("category") or conv.get("category") or "general"
    overview = structured.get("overview") or conv.get("overview") or ""
    source = conv.get("source") or "omi"

    desc_lines = [
        f"Category: {category}",
        f"Source: {source}",
    ]
    if overview:
        desc_lines.append(f"Overview: {overview}")

    segments = conv.get("transcript_segments") or []
    if isinstance(segments, list) and segments:
        desc_lines.append(f"Turns: {len(segments)}")

    description = ics_text("\n".join(desc_lines))
    created = ics_datetime(conv.get("created_at")) or start

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp(now_utc)}",
        f"DTSTART:{stamp(start)}",
        f"DTEND:{stamp(end)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"CATEGORIES:{ics_text(category)}",
        f"CREATED:{stamp(created)}",
        "END:VEVENT",
    ]
    return lines


def generate_ics(conversations: Sequence[Dict[str, Any]]) -> Tuple[str, int, int]:
    """Generate RFC 5545 iCalendar text from a sequence of conversations.

    Returns:
        (ics_content, event_count, skipped_count)
    """
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for conv in conversations:
        cid = str(conv.get("id"))
        if cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(conv)

    now_utc = datetime.now(timezone.utc)
    raw_lines: List[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    event_count = 0
    skipped_count = 0

    for conv in deduped:
        ev_lines = conversation_to_event(conv, now_utc)
        if ev_lines:
            raw_lines.extend(ev_lines)
            event_count += 1
        else:
            skipped_count += 1

    raw_lines.append("END:VCALENDAR")

    folded_lines: List[str] = []
    for line in raw_lines:
        folded_lines.extend(fold(line))

    ics_text_content = "\r\n".join(folded_lines) + "\r\n"
    return ics_text_content, event_count, skipped_count


def convert_paths_to_ics(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
) -> Tuple[int, int]:
    """Convert conversation JSON exports into an iCalendar file."""
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    ics_content, event_count, skipped_count = generate_ics(all_conversations)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(ics_content.encode("utf-8"))
    else:
        sys.stdout.write(ics_content)

    return event_count, skipped_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversations JSON exports into an iCalendar (.ics) file."
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
        help="Destination .ics file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        events, skipped = convert_paths_to_ics(args.inputs, args.output)
        if args.output != "-":
            print(
                f"Exported {events} calendar event(s) to {args.output} ({skipped} skipped without timestamp)",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
