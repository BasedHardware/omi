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

Save the following as `action_items_to_ics.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_LENGTH = timedelta(minutes=30)


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
    """Parse an ISO-8601 timestamp into an iCalendar UTC stamp, or None if unusable."""
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
        raise ValueError("Expected the JSON array from omi --json action-item list")
    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//action_items_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi action items"]
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        due = ics_datetime(item.get("due_at"))
        if due is None:
            skipped += 1
            continue
        item_id = ics_text(item.get("id")) or "unknown"
        description = ics_text(item.get("description")) or "(no description)"
        notes = [f"Omi action item {item_id}"]
        if item.get("conversation_id"):
            notes.append(f"Conversation: {ics_text(item.get('conversation_id'))}")
        created = ics_datetime(item.get("created_at"))
        lines += ["BEGIN:VEVENT", f"UID:omi-action-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(due)}", f"DTEND:{stamp(due + EVENT_LENGTH)}",
                  f"SUMMARY:{description}", "DESCRIPTION:" + "\\n".join(notes),
                  "STATUS:" + ("COMPLETED" if item.get("completed") else "CONFIRMED"),
                  "CATEGORIES:Omi"]
        if created is not None:
            lines.append(f"CREATED:{stamp(created)}")
        lines.append("END:VEVENT")
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
        sys.exit("Usage: python action_items_to_ics.py INPUT.json OUTPUT.ics")
    try:
        written, skipped = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} item(s) skipped (no due date)")
```

Run the converter:

```sh
python action_items_to_ics.py action_items.json action_items.ics
```

Import the file into your calendar (Google Calendar: Settings → Import & export;
Apple Calendar: File → Import; Outlook: File → Open & Export). Each item with a
due date becomes a 30-minute event starting at `due_at`, stored in UTC so your
calendar shows it in local time. The event UID is derived from the item ID, so
re-importing a fresh export updates the same events instead of duplicating them
in calendars that honour UIDs. Items without a due date are skipped and counted.
Commas, semicolons and line breaks in descriptions are escaped, long lines are
folded per RFC 5545, and the converter refuses to overwrite an existing file.
Treat the exported file as private data.
