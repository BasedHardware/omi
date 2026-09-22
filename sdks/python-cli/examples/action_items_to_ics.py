"""
Convert Omi action-item JSON exports to a standard iCalendar (.ics) file.

Each action item with a due date becomes a VTODO (task) entry, so the file
imports cleanly into Google Calendar, Apple Calendar/Reminders, Outlook, and
any RFC 5545 compatible client. Completed items are marked STATUS:COMPLETED.

Usage:
  python action_items_to_ics.py input.json -o tasks.ics
  omi --json action-item list | python action_items_to_ics.py - -o tasks.ics
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ics_dt(dt: datetime) -> str:
    """Format a UTC datetime as an iCalendar UTC timestamp (e.g. 20260922T173000Z)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def escape_text(value: str) -> str:
    """Escape a value per RFC 5545 (backslash, semicolon, comma, newline)."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold_line(line: str) -> str:
    """Fold a content line to 75 octets per RFC 5545 (continuation lines start with a space)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: List[bytes] = []
    # First chunk 75 bytes, subsequent chunks 74 bytes (leading space counts as 1).
    chunks.append(encoded[:75])
    rest = encoded[75:]
    while rest:
        chunks.append(rest[:74])
        rest = rest[74:]
    # Decode back carefully; split on byte boundaries may break multibyte chars,
    # so decode with 'ignore' only for safety of the folded transport form.
    out = chunks[0].decode("utf-8", "ignore")
    for c in chunks[1:]:
        out += "\r\n " + c.decode("utf-8", "ignore")
    return out


def is_completed(value: Any) -> bool:
    """Interpret loosely-typed 'completed' fields as a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return False


def load_items(source: str) -> List[Dict[str, Any]]:
    """Read action items from a JSON file path or '-' for stdin."""
    if source == "-":
        raw = sys.stdin.read().lstrip("\ufeff")
    else:
        raw = Path(source).read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("action_items") or data.get("items") or data.get("data") or [data]
    if not isinstance(data, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")
    return data


def build_calendar(items: List[Dict[str, Any]]) -> str:
    """Build an iCalendar document (VTODO per action item) from the items."""
    now = datetime.now(timezone.utc)
    stamp = ics_dt(now)

    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omi//action_items_to_ics//EN",
        "CALSCALE:GREGORIAN",
    ]

    count = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        description = item.get("description") or item.get("title") or "Untitled task"
        uid_source = item.get("id")
        uid = f"{uid_source}@omi" if uid_source else f"omi-action-{index}-{stamp}"
        due = parse_dt(item.get("due_at"))
        created = parse_dt(item.get("created_at"))
        completed = is_completed(item.get("completed"))

        vtodo: List[str] = [
            "BEGIN:VTODO",
            f"UID:{escape_text(str(uid))}",
            f"DTSTAMP:{stamp}",
            f"SUMMARY:{escape_text(str(description).strip())}",
        ]
        if created:
            vtodo.append(f"CREATED:{ics_dt(created)}")
        if due:
            vtodo.append(f"DUE:{ics_dt(due)}")
        vtodo.append("STATUS:COMPLETED" if completed else "STATUS:NEEDS-ACTION")
        if completed:
            vtodo.append("PERCENT-COMPLETE:100")
            vtodo.append(f"COMPLETED:{stamp}")
        conv_id = item.get("conversation_id")
        if conv_id:
            vtodo.append(f"X-OMI-CONVERSATION-ID:{escape_text(str(conv_id))}")
        vtodo.append("END:VTODO")

        lines.extend(vtodo)
        count += 1

    lines.append("END:VCALENDAR")

    # RFC 5545 requires CRLF line endings; fold long lines too.
    folded = [fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n", count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action-item JSON exports to an iCalendar (.ics) file."
    )
    parser.add_argument("input", help="Path to JSON file (or '-' for stdin).")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("action_items.ics"),
        help="Output .ics file (default: action_items.ics).",
    )
    args = parser.parse_args()

    items = load_items(args.input)
    ics_text, count = build_calendar(items)
    args.output.write_text(ics_text, encoding="utf-8")
    print(f"Wrote {count} task(s) to {args.output}")


if __name__ == "__main__":
    main()
