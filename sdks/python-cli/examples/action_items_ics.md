# Put open action items on your calendar (.ics)

Use this recipe to see Omi's open action items next to your meetings. It reads a
saved JSON export, makes no network requests, and writes one iCalendar file that
Google Calendar, Apple Calendar, Outlook and Thunderbird can import. Only items
with a `due_at` become events; the converter reports how many had no due date.
You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your open action items (up to 500):

```sh
omi --json action-item list --open --limit 500 > action_items.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename.

Save the following as `action_items_to_ics.py` (or run the bundled [`action_items_to_ics.py`](action_items_to_ics.py) directly):

```python
#!/usr/bin/env python3
"""Convert Omi action items JSON exports into an iCalendar (.ics) file.

Usage:
    python action_items_to_ics.py action_items.json -o tasks.ics
    omi --json action-item list --open | python action_items_to_ics.py - -o tasks.ics
    python action_items_to_ics.py page1.json page2.json -o all_tasks.ics

Generates an RFC 5545 compliant iCalendar (.ics) file compatible with Apple Calendar,
Google Calendar, Outlook, and Thunderbird.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVENT_LENGTH = timedelta(minutes=30)
PRODID = "-//Omi//omi-cli action_items_to_ics//EN"


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    Coerces non-null values safely to strings. Escapes backslashes, semicolons,
    commas, and newlines to ensure strict iCalendar standard compliance.
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
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 multi-byte character."""
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


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of action item dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action items object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each action item must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: action item missing required 'id' field")
        results.append(item)

    return results


def item_to_event(item: Dict[str, Any], now_utc: datetime) -> Optional[List[str]]:
    """Convert a single action item to an iCalendar VEVENT property block, or None if no due date."""
    due = ics_datetime(item.get("due_at"))
    if not due:
        return None

    item_id = str(item.get("id"))
    uid = f"{item_id}@omi"
    description = item.get("description") or "Untitled task"
    summary = ics_text(description)
    completed = bool(item.get("completed", False))
    status = "COMPLETED" if completed else "NEEDS-ACTION"

    created = ics_datetime(item.get("created_at"))
    end = due + EVENT_LENGTH

    conv_id = item.get("conversation_id")
    desc_lines = [f"Task: {description}"]
    if conv_id:
        desc_lines.append(f"Conversation: {conv_id}")
    desc_text = ics_text("\n".join(desc_lines))

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp(now_utc)}",
        f"DTSTART:{stamp(due)}",
        f"DTEND:{stamp(end)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc_text}",
        f"STATUS:{status}",
    ]
    if created is not None:
        lines.append(f"CREATED:{stamp(created)}")
    lines.append("END:VEVENT")
    return lines


def generate_ics(items: Sequence[Dict[str, Any]]) -> Tuple[str, int, int]:
    """Generate RFC 5545 iCalendar text from a sequence of action items.

    Returns:
        (ics_content, event_count, skipped_no_due_date_count)
    """
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        tid = str(it.get("id"))
        if tid not in seen_ids:
            seen_ids.add(tid)
            deduped.append(it)

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

    for it in deduped:
        ev_lines = item_to_event(it, now_utc)
        if ev_lines:
            raw_lines.extend(ev_lines)
            event_count += 1
        else:
            skipped_count += 1

    raw_lines.append("END:VCALENDAR")

    # Fold all content lines to 75 octets per RFC 5545 §3.1
    folded_lines: List[str] = []
    for line in raw_lines:
        folded_lines.extend(fold(line))

    # RFC 5545 requires CRLF line endings
    ics_text_content = "\r\n".join(folded_lines) + "\r\n"
    return ics_text_content, event_count, skipped_count


def convert_paths_to_ics(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
) -> Tuple[int, int]:
    """Convert action items JSON exports into an iCalendar file.

    Returns:
        (event_count, skipped_count)
    """
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    ics_content, event_count, skipped_count = generate_ics(all_items)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(ics_content.encode("utf-8"))
    else:
        sys.stdout.write(ics_content)

    return event_count, skipped_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into an iCalendar (.ics) file."
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
                f"Exported {events} calendar event(s) to {args.output} ({skipped} skipped without due date)",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Run the converter:

```sh
python action_items_to_ics.py action_items.json -o action_items.ics
```

Multiple export pages can also be merged in a single run:

```sh
python action_items_to_ics.py page1.json page2.json -o action_items.ics
```

Or stream directly from the CLI without intermediate files:

```sh
omi --json action-item list --open | python action_items_to_ics.py - -o action_items.ics
```

Import the file into your calendar (Google Calendar: Settings → Import & export;
Apple Calendar: File → Import; Outlook: File → Open & Export). Each item with a
due date becomes a 30-minute event starting at `due_at`, stored in UTC so your
calendar shows it in local time. The event UID is `{id}@omi`, so re-importing a
fresh export updates the same events instead of duplicating them in calendars that
honour UIDs. Items without a due date are skipped and counted. Commas, semicolons
and line breaks in descriptions are escaped, long lines are folded per RFC 5545,
and `STATUS` is set to `NEEDS-ACTION` for open tasks and `COMPLETED` for finished
tasks. Treat the exported file as private data.
