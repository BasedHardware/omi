# Turn action items into a TaskPaper file

Use this recipe to keep Omi's action items in the plain-text
[TaskPaper](https://guide.taskpaper.com/getting-started/) format, which is read
by TaskPaper, Taskmator, the VS Code and Sublime Text TaskPaper modes, and any
text editor. It reads a saved JSON export, makes no network requests, and
writes an `Open:` project and a `Done:` project with one `- ` task per item: a
`due_at` becomes a `@due(...)` tag and completed items get `@done(...)`. You
need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 500 action items, open and completed:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename. Add
`--open` to export only the items that still need doing.

Save the following as `action_items_to_taskpaper.py` (the same script is kept
next to this recipe as [`action_items_to_taskpaper.py`](action_items_to_taskpaper.py)
and covered by `tests/test_action_items_to_taskpaper.py`):

```python
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed"}
ZWSP = "​"  # zero-width space: breaks TaskPaper syntax without changing the text
TAG_VALUE = re.compile(r"[A-Za-z0-9._:-]+")


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
    """Keep a description from being read as TaskPaper tags."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] == "@":
            word = ZWSP + word  # would otherwise become a tag such as @done
        words.append(word)
    return " ".join(words) or "(no description)"


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
    """Parse an ISO-8601 timestamp into local time, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def task_line(item, due, done, zone):
    parts = ["\t-", task_text(item.get("description"))]
    if due is not None:
        parts.append(f"@due({due:%Y-%m-%d %H:%M})")
    if done:
        completed = local_time(item.get("completed_at"), zone)
        parts.append(f"@done({completed:%Y-%m-%d})" if completed else "@done")
    created = local_time(item.get("created_at"), zone)
    if created is not None:
        parts.append(f"@created({created:%Y-%m-%d})")
    omi_id = one_line(item.get("id"))
    if TAG_VALUE.fullmatch(omi_id):
        parts.append(f"@omi({omi_id})")
    return " ".join(parts)


def convert(source, destination, zone):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    groups = {False: [], True: []}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        groups[is_done(item.get("completed"))].append((local_time(item.get("due_at"), zone), item))
    lines = []
    for done, project in ((False, "Open:"), (True, "Done:")):
        if not groups[done]:
            continue
        # Soonest due date first; items without a due date follow.
        groups[done].sort(key=lambda e: (e[0] is None, e[0] or datetime.min.replace(tzinfo=timezone.utc)))
        lines.append(project)
        lines.extend(task_line(item, due, done, zone) for due, item in groups[done])
    undated = sum(1 for group in groups.values() for due, _ in group if due is None)
    # Build the whole file before touching the filesystem, so a conversion
    # failure cannot leave a truncated .taskpaper file behind.
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
    return len(groups[False]), len(groups[True]), undated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to TaskPaper.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new .taskpaper file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="use local times at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        open_count, done_count, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"TaskPaper export failed: {exc}")
    print(f"{open_count} open and {done_count} done task(s) written, {undated} without a due date")
```

Run the converter:

```sh
python action_items_to_taskpaper.py action_items.json omi.taskpaper
```

Open `omi.taskpaper` in TaskPaper or a TaskPaper-aware editor. Open items come
first, sorted by due date, and items without a due date are kept and counted,
not dropped. Each task carries `@due(YYYY-MM-DD HH:MM)` when the item has a due
date, `@created(YYYY-MM-DD)`, and an `@omi(<id>)` tag with the Omi item ID, so
you can find an item again with `omi action-item get`; completed items carry
`@done` with their completion date when the export has one. TaskPaper dates
have no time zone, so times are shown in this computer's time zone; pass
`--utc-offset +09:00` (for example) to choose another offset. Descriptions are
collapsed to one line, and words that TaskPaper would otherwise read as a tag
(`@word`) are escaped with a zero-width space. Loosely typed fields are
coerced rather than rejected, the converter refuses to overwrite an existing
file, and a failed write leaves no partial file behind. Treat the exported
file as private data.
