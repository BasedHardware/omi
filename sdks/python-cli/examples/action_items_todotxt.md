# Turn action items into a todo.txt file

Use this recipe to keep Omi's action items in the plain-text
[todo.txt](https://github.com/todotxt/todo.txt) format, which is read by the
todo.txt CLI, Simpletask, sleek, Markor and many other apps. It reads a saved
JSON export, makes no network requests, and writes one task per line: open
items as plain tasks, completed items with the `x` marker, and a `due_at` as a
`due:YYYY-MM-DD` tag. You need Python 3.10+ and an authenticated `omi-cli` for
the initial export.

Export up to 500 action items, open and completed:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename. Add
`--open` to export only the items that still need doing.

Save the following as `action_items_to_todotxt.py` (the same script is kept
next to this recipe as [`action_items_to_todotxt.py`](action_items_to_todotxt.py)
and covered by `tests/test_action_items_to_todotxt.py`):

```python
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed"}
RESERVED_KEYS = {"due", "t", "rec", "h", "pri", "omi"}
ZWSP = "​"  # zero-width space: breaks todo.txt syntax without changing the text


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


def task_text(value):
    """Keep a description from being read as todo.txt syntax."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word  # would otherwise become a project or context
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"  # would otherwise override due:, omi:, ...
        words.append(word)
    text = " ".join(words) or "(no description)"
    if re.match(r"x |\([A-Z]\) |\d{4}-\d{2}-\d{2}( |$)", text):
        text = ZWSP + text  # would otherwise become a completion mark, priority or date
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


def local_date(value, zone):
    """Parse an ISO-8601 timestamp into the local calendar date, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).date()


def task_line(done, due, item, zone):
    parts = []
    created = local_date(item.get("created_at"), zone)
    if done:
        parts.append("x")
        completed = local_date(item.get("completed_at"), zone)
        # todo.txt reads the first date after "x" as the completion date, so the
        # creation date is written only when a completion date precedes it.
        if completed is not None:
            parts.append(completed.isoformat())
            if created is not None:
                parts.append(created.isoformat())
    elif created is not None:
        parts.append(created.isoformat())
    parts.append(task_text(item.get("description")))
    if due is not None:
        parts.append(f"due:{due.isoformat()}")
    omi_id = one_line(item.get("id"))
    if omi_id and " " not in omi_id:
        parts.append(f"omi:{omi_id}")
    return " ".join(parts)


def convert(source, destination, zone):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        entries.append((is_done(item.get("completed")), local_date(item.get("due_at"), zone), item))
    # Open items first, soonest due date first; items without a due date follow.
    entries.sort(key=lambda e: (e[0], e[1] is None, e[1] or datetime.min.date()))
    lines = [task_line(done, due, item, zone) for done, due, item in entries]
    undated = sum(1 for _, due, _ in entries if due is None)
    # Build the whole file before touching the filesystem, so a conversion
    # failure cannot leave a truncated todo.txt behind.
    payload = "".join(line + "\n" for line in lines).encode("utf-8")
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
    return len(lines), undated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to todo.txt.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new todo.txt file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="use calendar dates at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"todo.txt export failed: {exc}")
    print(f"{written} task(s) written, {undated} without a due date")
```

Run the converter:

```sh
python action_items_to_todotxt.py action_items.json omi_todo.txt
```

Open `omi_todo.txt` in any todo.txt app, or append it to the file you already
use. Open items come first, sorted by due date, and items without a due date
are kept and counted, not dropped. Each line carries the creation date, a
`due:` tag when the item has a due date, and an `omi:` tag with the Omi item
ID, so you can find an item again with `omi action-item get`. Completed items
start with `x` and their completion date. todo.txt dates have no time zone, so
the dates are the calendar days in this computer's time zone; pass
`--utc-offset +09:00` (for example) to choose another offset. Descriptions are
collapsed to one line, and words that todo.txt would otherwise read as a
project (`+word`), a context (`@word`), a `due:`/`omi:`-style tag, a priority
or a date are escaped with a zero-width space. Loosely typed fields are
coerced rather than rejected, the converter refuses to overwrite an existing
file, and a failed write leaves no partial file behind. Treat the exported
file as private data.
