# Put memories on your calendar (.ics)

Use this recipe to see your Omi memories, learnings, and captured insights
alongside your meetings and daily schedule. It reads a saved JSON export, makes
no network requests, and writes an iCalendar (.ics) file that Google Calendar,
Apple Calendar, Microsoft Outlook, and Thunderbird can import directly. It uses
only Python's standard library with zero external dependencies.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export:

Export your memories (up to 500):

```sh
omi --json memory list --limit 500 > memories.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename.

Save the following as `memories_to_ics.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_LENGTH = timedelta(minutes=15)


def ics_text(value):
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one unexpected row cannot break
    the entire calendar file.
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


def ics_datetime(value):
    """Parse an ISO-8601 timestamp into an iCalendar UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stamp(dt):
    """Format a UTC datetime as an iCalendar date-time string (YYYYMMDDTHHMMSSZ)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line):
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts, chunk, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk, limit = b" " + b, 75
        else:
            chunk += b
    parts.append(chunk.decode("utf-8"))
    return parts


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")

    now = stamp(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//omi-cli examples//memories_to_ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Omi memories",
    ]

    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")

        created = ics_datetime(item.get("created_at"))
        if created is None:
            skipped += 1
            continue

        item_id = ics_text(item.get("id")) or "unknown"
        content_raw = item.get("content") or "(empty memory)"
        first_line = content_raw.strip().split("\n")[0]
        summary = ics_text(first_line[:80] + ("..." if len(first_line) > 80 else ""))

        category = ics_text(item.get("category") or "other")
        origin = "Manually added" if item.get("manually_added") else "Captured by AI"

        desc_parts = [
            ics_text(content_raw),
            f"Category: {category}",
            f"Origin: {origin}",
            f"Memory ID: {item_id}",
        ]
        if item.get("conversation_id"):
            desc_parts.append(f"Conversation: {ics_text(item.get('conversation_id'))}")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:omi-memory-{item_id}@omi-cli",
            f"DTSTAMP:{now}",
            f"DTSTART:{stamp(created)}",
            f"DTEND:{stamp(created + EVENT_LENGTH)}",
            f"SUMMARY:{summary}",
            "DESCRIPTION:" + "\\n".join(desc_parts),
            f"CATEGORIES:{category}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    folded = [part for line in lines for part in fold(line)]
    payload = ("\r\n".join(folded) + "\r\n").encode("utf-8")
    output_path = Path(destination)

    # Exclusive creation protects an existing export; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise

    return len(items) - skipped, skipped


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_ics.py INPUT.json OUTPUT.ics")
    try:
        written, skipped = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} item(s) skipped (no created_at timestamp)")
```

Run the converter:

```sh
python memories_to_ics.py memories.json memories.ics
```

Import `memories.ics` into Google Calendar (Settings -> Import & Export), Apple
Calendar (File -> Import), or Outlook. Each memory appears at its recorded
`created_at` timestamp with a 15-minute slot, categorized and searchable. The
RFC 5545 line folding ensures long notes and multi-byte UTF-8 characters are
valid across all standard calendar clients.
