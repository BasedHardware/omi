# Put your conversation history on a calendar (.ics)

Use this recipe to see when Omi conversations happened, next to your meetings.
It reads a saved JSON export, makes no network requests, does not export
transcripts, and writes one iCalendar file that Google Calendar, Apple Calendar,
Outlook and Thunderbird can import. Each conversation with a `started_at`
becomes an event spanning `started_at`–`finished_at` (30 minutes if
`finished_at` is missing). You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup; to retrieve another page, increase `--offset` by
200 and use a different filename.

Save the following as `conversations_to_ics.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LENGTH = timedelta(minutes=30)


def ics_text(value):
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one odd row cannot break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_datetime(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
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
        raise ValueError("Expected the JSON array from omi --json conversation list")
    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//conversations_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi conversations"]
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        start = ics_datetime(item.get("started_at"))
        if start is None:
            skipped += 1
            continue
        end = ics_datetime(item.get("finished_at"))
        if end is None or end <= start:
            end = start + DEFAULT_LENGTH
        item_id = ics_text(item.get("id")) or "unknown"
        title = ics_text(structured.get("title")) or "(untitled conversation)"
        notes = [f"Omi conversation {item_id}"]
        for label, key in (("Category", "category"),):
            if structured.get(key):
                notes.append(f"{label}: {ics_text(structured.get(key))}")
        if item.get("source"):
            notes.append(f"Source: {ics_text(item.get('source'))}")
        lines += ["BEGIN:VEVENT", f"UID:omi-conversation-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(start)}", f"DTEND:{stamp(end)}", f"SUMMARY:{title}",
                  "DESCRIPTION:" + "\\n".join(notes), "STATUS:CONFIRMED", "CATEGORIES:Omi", "END:VEVENT"]
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
        sys.exit("Usage: python conversations_to_ics.py INPUT.json OUTPUT.ics")
    try:
        written, skipped = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} conversation(s) skipped (no start time)")
```

Run the converter:

```sh
python conversations_to_ics.py conversations.json conversations.ics
```

Import the file into your calendar (Google Calendar: Settings → Import & export;
Apple Calendar: File → Import; Outlook: File → Open & Export). Times are stored
in UTC, so the calendar shows them in your local time zone. The event UID is
derived from the conversation ID, so re-importing a fresh export updates the same
events instead of duplicating them in calendars that honour UIDs. Conversations
without a start time are skipped and counted. Titles containing commas,
semicolons or line breaks are escaped, long lines are folded per RFC 5545, and
the converter refuses to overwrite an existing file. Treat the exported file as
private conversation data.
