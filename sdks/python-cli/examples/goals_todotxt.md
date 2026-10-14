# Convert a goal export to todo.txt

Use this recipe to mirror your Omi goals into a standard `todo.txt` file that
works with todo.txt apps, Simpletask, sleek, or plain-text workflows. Each goal
becomes one task line: `achieved` goals are marked done (`x`), `focused` goals
map to priorities `(A)`–`(C)` from `focus_rank`, `horizon_at` becomes a
`due:` date, progress becomes `progress:current/target`, and `goal_id` becomes
an `omi:` key so a later run can recognise it. You need Python 3.10+ and an
authenticated `omi-cli` for the export.

Export your goals:

```sh
omi --json goal list > goals.json
```

Check that the command succeeded before converting. Save the following as
`goals_to_todotxt.py`:

```python
"""Convert an Omi goal export to a todo.txt file."""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed", "achieved"}
RESERVED_KEYS = {"due", "t", "rec", "h", "pri", "omi"}
ZWSP = "​"


def strip_surrogates(value: str) -> str:
    return value.encode("utf-8", "ignore").decode("utf-8")


def one_line(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(strip_surrogates(value).split())


def task_text(value):
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"
        words.append(word)
    text = " ".join(words) or "(untitled goal)"
    if re.match(r"(?:x|\([A-Z]\)|\d{4}-\d{2}-\d{2})(?: |$)", text):
        text = ZWSP + text
    return text


def parse_offset(text):
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    return timezone(delta if match.group(1) == "+" else -delta)


def local_date(value, zone):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).date()


def is_achieved(item):
    status = item.get("status")
    if isinstance(status, str) and status.strip().lower() == "achieved":
        return True
    return item.get("completed") in (True, "true", 1)


def progress_note(item):
    current = item.get("current_value")
    target = item.get("target_value")
    metric = item.get("metric")
    if (current is None or target is None) and isinstance(metric, dict):
        current = metric.get("current_value") if current is None else current
        target = metric.get("target_value") if target is None else target
    if current is None or target is None:
        return ""
    try:
        cur, tgt = float(current), float(target)
    except (TypeError, ValueError):
        return ""
    unit = one_line(item.get("unit"))
    return f"progress:{cur:g}/{tgt:g}" + (f" {unit}" if unit else "")


def priority_letter(item):
    rank = item.get("focus_rank")
    if isinstance(rank, bool):
        return None
    if isinstance(rank, (int, float)) and int(rank) in (1, 2, 3):
        return chr(ord("A") + int(rank) - 1)
    return None


def task_line(item, zone):
    parts = []
    created = local_date(item.get("created_at"), zone)
    if is_achieved(item):
        parts.append("x")
        ended = local_date(item.get("ended_at"), zone) or local_date(item.get("updated_at"), zone)
        if ended is not None:
            parts.append(ended.isoformat())
            if created is not None:
                parts.append(created.isoformat())
    else:
        pri = priority_letter(item)
        if pri:
            parts.append(f"({pri})")
        elif created is not None:
            parts.append(created.isoformat())
    parts.append(task_text(item.get("title") or item.get("desired_outcome")))
    note = progress_note(item)
    if note:
        parts.append(note)
    if isinstance(item.get("status"), str) and item["status"].strip().lower() == "abandoned":
        parts.append("status:abandoned")
    due = local_date(item.get("horizon_at"), zone)
    if due is not None:
        parts.append(f"due:{due.isoformat()}")
    goal_id = one_line(item.get("goal_id") or item.get("id"))
    if goal_id and " " not in goal_id:
        parts.append(f"omi:{goal_id}")
    return " ".join(parts)


def extract_goals(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def convert(source, destination, zone):
    raw = json.loads(Path(source).read_bytes().decode("utf-8-sig"))
    items = extract_goals(raw)
    if items is None or not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")
    entries = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")
        entries.append((is_achieved(item), priority_letter(item) or "Z",
                        local_date(item.get("horizon_at"), zone), item))
    entries.sort(key=lambda e: (e[0], e[1], e[2] is None, e[2] or datetime.min.date()))
    lines = [task_line(item, zone) for _, _, _, item in entries]
    undated = sum(1 for _, _, due, _ in entries if due is None)
    payload = strip_surrogates("".join(line + "\n" for line in lines)).encode("utf-8")
    output_path = Path(destination)
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
    parser = argparse.ArgumentParser(description="Convert an omi goal export to todo.txt.")
    parser.add_argument("source", help="JSON from omi --json goal list")
    parser.add_argument("destination", help="new todo.txt file to create")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="use calendar dates at this offset (e.g. +09:00); default: this computer's time zone")
    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, undated = convert(args.source, args.destination, zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"todo.txt export failed: {exc}")
    print(f"{written} goal(s) written, {undated} without a horizon date")
```

Convert the export:

```sh
python goals_to_todotxt.py goals.json omi_goals.txt
```

Pin a specific reporting time zone if you run the export for someone else's
calendar (dates are written as local calendar dates; pass `--utc-offset +HH:MM`
to choose the zone explicitly):

```sh
python goals_to_todotxt.py goals.json omi_goals.txt --utc-offset +09:00
```

The output opens in any todo.txt client. Open goals sort first by focus rank
(`(A)`/`(B)`/`(C)`), then by soonest `due:`; achieved goals drop to the bottom
marked `x`. Titles that would collide with todo.txt syntax (a leading `+`,
`@`, `x`, `(A)` or a bare date) are defused with an invisible zero-width space
so they render as plain text instead of being parsed as syntax. The destination
file is created exclusively and is never overwritten — delete it first if you
want to regenerate. A recognised wrapper (`goals`, `items`, `data`, or
`results`) holding an empty list produces an empty but valid file.
