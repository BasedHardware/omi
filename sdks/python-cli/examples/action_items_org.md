# Turn action items into an Org-mode agenda file

Use this recipe to work through Omi's action items in Emacs Org mode, or in an
Org app such as Orgzly or beorg. It reads a saved JSON export, makes no network
requests, and writes one `.org` file: every action item becomes a `TODO` or
`DONE` heading, and a `due_at` becomes a `DEADLINE`, so the items show up in
your Org agenda next to everything else. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

Export up to 500 action items, open and completed:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename. Add
`--open` to export only the items that still need doing.

Save the following as `action_items_to_org.py` (the same script is kept next to
this recipe as [`action_items_to_org.py`](action_items_to_org.py) and covered
by `tests/test_action_items_to_org.py`):

```python
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DONE_WORDS = {"true", "yes", "1", "done", "completed"}
ZWSP = "​"  # zero-width space, Org's documented escape character


def one_line(value):
    """Render one exported field as single-line text.

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one odd row cannot break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value):
    """Keep a description from being parsed as Org syntax inside a heading."""
    text = one_line(value) or "(no description)"
    if text.startswith("[#"):
        text = ZWSP + text  # would otherwise become a priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # no stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # would otherwise become heading tags
    return text


def is_done(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return isinstance(value, str) and value.strip().lower() in DONE_WORDS


def parse_offset(text):
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_time(value, zone):
    """Parse an ISO-8601 timestamp into local wall-clock time, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def org_stamp(dt, active):
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def convert(source, destination, zone):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        done = is_done(item.get("completed"))
        due = local_time(item.get("due_at"), zone)
        entries.append((done, due, item))
    # Open items first, soonest deadline first; items without a deadline follow.
    entries.sort(key=lambda e: (e[0], e[1] is None, e[1].timestamp() if e[1] else 0.0))
    lines = ["# -*- mode: org; coding: utf-8 -*-", "#+TITLE: Omi action items", ""]
    undated = 0
    for done, due, item in entries:
        lines.append(f"* {'DONE' if done else 'TODO'} {heading_text(item.get('description'))}")
        planning = []
        closed = local_time(item.get("completed_at"), zone) if done else None
        if closed is not None:
            planning.append("CLOSED: " + org_stamp(closed, active=False))
        if due is not None:
            planning.append("DEADLINE: " + org_stamp(due, active=True))
        else:
            undated += 1
        if planning:
            lines.append(" ".join(planning))
        lines.append(":PROPERTIES:")
        for key, value in (("OMI_ID", one_line(item.get("id"))),
                           ("CONVERSATION", one_line(item.get("conversation_id")))):
            if value:
                lines.append(f":{key}: {value}")
        created = local_time(item.get("created_at"), zone)
        if created is not None:
            lines.append(":CREATED: " + org_stamp(created, active=False))
        lines.append(":END:")
    # Build the whole file before touching the filesystem, so a conversion
    # failure cannot leave a truncated .org file behind.
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing file; a failed write leaves no partial file.
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
    return len(entries), undated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to an Org file.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new .org file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="write times at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")
    print(f"{written} heading(s) written, {undated} without a deadline")
```

Run the converter:

```sh
python action_items_to_org.py action_items.json omi_action_items.org
```

Add the file to `org-agenda-files` (or open it in Orgzly or beorg) and the
items with a due date appear in the agenda on their deadline. Open items come
first, sorted by deadline; items without a due date are kept as plain `TODO`
headings and counted, not dropped. Completed items become `DONE`, with a
`CLOSED` timestamp when `completed_at` is present. The Omi item ID, the source
conversation ID and the creation time are kept in each heading's property
drawer, so you can find an item again with `omi action-item get`. Org
timestamps have no time zone, so times are written in this computer's local
time; pass `--utc-offset +09:00` (for example) to choose another offset.
Descriptions are collapsed to one line, and text that Org would otherwise read
as a priority, tags or an agenda timestamp is escaped with a zero-width space.
Loosely typed fields are coerced rather than rejected, the converter refuses to
overwrite an existing file, and a failed write leaves no partial file behind.
Treat the exported file as private data.
