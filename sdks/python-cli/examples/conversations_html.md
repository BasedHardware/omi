# Build a self-contained HTML report of your conversations

Use this recipe to browse or print a period of Omi conversations without the
CLI or a spreadsheet: it turns one or more `conversation list` exports into a
single HTML file with a summary line, one section per day and a table of the
conversations recorded that day (start time, duration, title, category, folder,
source, language, ID). It reads saved JSON exports, makes no network requests,
does not export transcripts, and writes one HTML file with no scripts, external
stylesheets or images. You need Python 3.10+ and an authenticated `omi-cli` for
the initial export.

Export the period you want to report on (200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 --start-date 2026-09-14T00:00:00Z --end-date 2026-09-21T00:00:00Z > week.json
```

Check that the command succeeded before converting the file. If a page is
full, retrieve the next one with `--offset 200` into a second file; the report
accepts several files and lists each conversation ID once.

Save the following as `conversations_html.py`:

```python
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

COLUMNS = ("Start", "Duration", "Title", "Category", "Folder", "Source", "Language", "ID")

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #1a1a1a; background: #fff; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc; }
p.summary { color: #444; } table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }
th { background: #f3f3f3; } td.num { text-align: right; white-space: nowrap; } td.id { font-family: monospace; font-size: 0.8rem; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } tr { page-break-inside: avoid; } }
"""


def text(value):
    """Render a loosely typed field as one line of text; anything non-null is coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value):
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


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar days and clock times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: expected the JSON array from omi --json conversation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each conversation must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: each conversation needs a string id")
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: conversation structured field must be an object or null")
            conversations[item_id] = item
    return conversations


def rows_by_day(conversations, offset):
    """Group conversations into local calendar days; returns (days, undated) with rows sorted by start."""
    days, undated = defaultdict(list), []
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        structured = item.get("structured") or {}
        seconds = int((end - start).total_seconds()) if start is not None and end is not None and end >= start else 0
        row = {
            "start": (start + offset).strftime("%H:%M") if start is not None else "",
            "sort": start if start is not None else datetime.max.replace(tzinfo=timezone.utc),
            "seconds": seconds,
            "title": text(structured.get("title")) or "(untitled conversation)",
            "category": text(structured.get("category")),
            "folder": text(item.get("folder_name")),
            "source": text(item.get("source")),
            "language": text(item.get("language")),
            "id": item_id,
        }
        if start is None:
            undated.append(row)
        else:
            days[(start + offset).strftime("%Y-%m-%d")].append(row)
    for bucket in list(days.values()) + [undated]:
        bucket.sort(key=lambda row: (row["sort"], row["id"]))
    return dict(sorted(days.items())), undated


def minutes(seconds):
    return f"{seconds / 60:.0f} min"


def table(rows):
    lines = ["<table>", "<thead><tr>" + "".join(f"<th>{escape(column)}</th>" for column in COLUMNS) + "</tr></thead>", "<tbody>"]
    for row in rows:
        cells = [
            f"<td class=\"num\">{escape(row['start'])}</td>",
            f"<td class=\"num\">{escape(minutes(row['seconds']))}</td>",
            f"<td>{escape(row['title'])}</td>",
            f"<td>{escape(row['category'])}</td>",
            f"<td>{escape(row['folder'])}</td>",
            f"<td>{escape(row['source'])}</td>",
            f"<td>{escape(row['language'])}</td>",
            f"<td class=\"id\">{escape(row['id'])}</td>",
        ]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines += ["</tbody>", "</table>"]
    return "\n".join(lines)


def report(conversations, offset, offset_label):
    days, undated = rows_by_day(conversations, offset)
    total = sum(len(rows) for rows in days.values())
    total_seconds = sum(row["seconds"] for rows in days.values() for row in rows)
    summary = f"Conversations: {total} · Recorded time: {total_seconds / 3600:.1f} h · Days with recordings: {len(days)}"
    if undated:
        summary += f" · Undated: {len(undated)}"
    parts = ["<!DOCTYPE html>", "<html lang=\"en\">", "<head>", "<meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
             "<title>Omi conversation report</title>", f"<style>{STYLE}</style>", "</head>", "<body>",
             "<h1>Omi conversation report</h1>",
             f"<p class=\"summary\">{escape(summary)}<br>Times shown in UTC{escape(offset_label)}.</p>"]
    if not days and not undated:
        parts.append("<p>No conversations in the export.</p>")
    for day, rows in days.items():
        day_seconds = sum(row["seconds"] for row in rows)
        parts += [f"<h2 id=\"d{escape(day)}\">{escape(day)}</h2>",
                  f"<p class=\"summary\">{len(rows)} conversation{'s' if len(rows) != 1 else ''} · {day_seconds / 3600:.1f} h</p>",
                  table(rows)]
    if undated:
        parts += ["<h2 id=\"undated\">Undated</h2>",
                  f"<p class=\"summary\">{len(undated)} conversation{'s' if len(undated) != 1 else ''} without a start time</p>",
                  table(undated)]
    parts += ["</body>", "</html>"]
    return "\n".join(parts) + "\n"


def convert(sources, destination, offset, offset_label):
    payload = report(load(sources), offset, offset_label).encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing report; a failed write leaves no partial file.
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


if __name__ == "__main__":
    args = sys.argv[1:]
    offset, offset_label = timedelta(0), ""
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            offset = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"Report failed: {exc}")
        offset_label = args[1]
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python conversations_html.py [--utc-offset +09:00] OUTPUT.html INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], offset, offset_label)
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")
    print(f"report written to {args[0]}")
```

Run it (the output file comes first, then one or more exports):

```sh
python conversations_html.py --utc-offset +09:00 week.html week.json
```

Open `week.html` in any browser; it also prints cleanly, one day per heading.
The summary line counts conversations, recorded hours and days; each day
section lists that day's conversations in start order with their duration
(`finished_at − started_at`, `0 min` when the end is missing or earlier than
the start), title, category, folder, source, language and ID. Days and clock
times use the time zone you pass with `--utc-offset`; omit it for UTC. A
conversation without a usable start time is listed in an "Undated" section at
the end. Titles and categories come from the `structured` object the API
returns, so no transcript text is read or written, and every value is
HTML-escaped, so a title containing `<` or `&` is shown literally rather than
interpreted. The script refuses to overwrite an existing report, so use one
file per period. Treat the file as private data.
