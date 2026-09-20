# Build a compact conversation digest

This recipe combines one or more saved `omi --json conversation list` pages
into a short Markdown report. It reads only `id`, `structured.title`,
`structured.category`, `started_at`, and `finished_at`; it never reads or
prints transcript text and makes no network requests. If pages overlap, the
last row with a given conversation `id` wins.

Create a digest in UTC:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations_0.json
omi --json conversation list --limit 200 --offset 200 > conversations_200.json
python conversations_digest.py conversations_0.json conversations_200.json \
  --output ConversationDigest.md
```

Use a local calendar day without installing timezone data (for example,
Shanghai/Tokyo time):

```sh
python conversations_digest.py conversations_0.json --utc-offset +09:00 \
  --output ConversationDigest.md
```

Save the following as `conversations_digest.py`:

```python
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


UTC = timezone.utc
_WRAPPER_KEYS = ("conversations", "items", "data")


def read_json(source):
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        raw = Path(source).read_bytes()
    return json.loads(raw.decode("utf-8-sig"))


def page_items(source):
    value = read_json(source)
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = None
        for key in _WRAPPER_KEYS:
            if key in value:
                items = value[key]
                break
        if not isinstance(items, list):
            raise ValueError(f"{source}: expected a JSON array of conversations")
    else:
        raise ValueError(f"{source}: expected a JSON array of conversations")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: item {index} must be an object")
    return items


def text(value, fallback=""):
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_offset(value):
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if not match:
        raise ValueError("utc offset must look like +09:00 or -05:30")
    hours = int(match.group(2))
    minutes = int(match.group(3))
    if hours > 23:
        raise ValueError("utc offset hours must be between 00 and 23")
    total_minutes = hours * 60 + minutes
    if match.group(1) == "-":
        total_minutes = -total_minutes
    return timezone(timedelta(minutes=total_minutes)), value


def load_items(sources):
    merged = {}
    for source in sources:
        for item in page_items(source):
            conversation_id = item.get("id")
            if conversation_id is None or not text(conversation_id).strip():
                raise ValueError(f"{source}: every conversation must have a non-empty id")
            merged[text(conversation_id)] = item
    return list(merged.values())


def structured(item):
    value = item.get("structured")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("conversation structured field must be an object or null")
    return value


def table_text(value, fallback):
    rendered = text(value, fallback)
    rendered = rendered.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    rendered = re.sub(r"\s+", " ", rendered).strip() or fallback
    return rendered.replace("|", "\\|")


def analyse(items, local_zone):
    included = []
    skipped = 0
    for item in items:
        details = structured(item)
        started = parse_timestamp(item.get("started_at"))
        if started is None:
            skipped += 1
            continue
        finished = parse_timestamp(item.get("finished_at"))
        duration = 0.0
        if finished is not None and finished > started:
            duration = (finished - started).total_seconds()
        included.append({
            "id": text(item.get("id")),
            "title": table_text(details.get("title"), "(untitled)"),
            "category": table_text(details.get("category"), "Uncategorized"),
            "started": started,
            "date": started.astimezone(local_zone).date(),
            "duration": duration,
        })
    return included, skipped


def hours(seconds):
    return f"{seconds / 3600:.2f}"


def render(items, offset_value):
    local_zone, offset_label = parse_offset(offset_value)
    records, skipped = analyse(items, local_zone)
    total_seconds = sum(record["duration"] for record in records)
    by_day = defaultdict(lambda: {"count": 0, "seconds": 0.0})
    by_category = defaultdict(lambda: {"count": 0, "seconds": 0.0})
    for record in records:
        by_day[record["date"]]["count"] += 1
        by_day[record["date"]]["seconds"] += record["duration"]
        by_category[record["category"]]["count"] += 1
        by_category[record["category"]]["seconds"] += record["duration"]

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "---",
        "type: omi-conversation-digest",
        f"conversations: {len(records)}",
        f"skipped_without_start: {skipped}",
        f"recorded_hours: {hours(total_seconds)}",
        f'utc_offset: "{offset_label}"',
        f'exported_at: "{now}"',
        "---",
        "",
        "# Omi Conversation Digest",
        "",
        f"Calendar grouping uses UTC{offset_label}; conversations without a valid start are skipped.",
        "",
        "## Summary",
        "",
        f"- Included conversations: {len(records)}",
        f"- Skipped without a valid start: {skipped}",
        f"- Recorded hours (valid positive intervals only): {hours(total_seconds)}",
        "",
        "## By day",
        "",
        "| Date | Conversations | Recorded hours |",
        "| --- | ---: | ---: |",
    ]
    if by_day:
        for day in sorted(by_day):
            value = by_day[day]
            lines.append(f"| {day.isoformat()} | {value['count']} | {hours(value['seconds'])} |")
    else:
        lines.append("| — | 0 | 0.00 |")

    lines.extend([
        "",
        "## By category",
        "",
        "| Category | Conversations | Recorded hours |",
        "| --- | ---: | ---: |",
    ])
    if by_category:
        for category in sorted(by_category, key=str.casefold):
            value = by_category[category]
            lines.append(f"| {category} | {value['count']} | {hours(value['seconds'])} |")
    else:
        lines.append("| — | 0 | 0.00 |")

    lines.extend([
        "",
        "## Five longest conversations",
        "",
        "| Rank | Title | ID | Recorded hours |",
        "| ---: | --- | --- | ---: |",
    ])
    longest = sorted(records, key=lambda record: (-record["duration"], record["started"], record["id"]))[:5]
    if longest:
        for rank, record in enumerate(longest, start=1):
            lines.append(
                f"| {rank} | {record['title']} | `{record['id']}` | {hours(record['duration'])} |"
            )
    else:
        lines.append("| — | No conversations with a valid start | — | 0.00 |")
    return "\n".join(lines) + "\n"


def write_exclusive(destination, payload):
    output_path = Path(destination)
    created = False
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as output:
            created = True
            output.write(payload)
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    except OSError:
        if created:
            output_path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSON page paths, or - for stdin")
    parser.add_argument("--utc-offset", default="+00:00", help="fixed offset such as +09:00")
    parser.add_argument("-o", "--output", required=True, help="new Markdown output path")
    args = parser.parse_args(argv)
    if args.inputs.count("-") > 1:
        parser.error("stdin may be used for only one input page")
    try:
        # Validate the offset and all pages before creating the destination.
        parse_offset(args.utc_offset)
        write_exclusive(args.output, render(load_items(args.inputs), args.utc_offset))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"conversation digest failed: {exc}\n")


if __name__ == "__main__":
    main()
```

The report includes per-day counts and hours, per-category counts and hours,
the five longest conversations with IDs, and a clear count of rows skipped for
missing or invalid `started_at`. A missing or non-increasing `finished_at`
keeps the conversation in the count but contributes zero recorded hours.
`--utc-offset` accepts a fixed `+HH:MM` or `-HH:MM` offset and is applied only
for day grouping; timestamps are still parsed as UTC internally. Invalid
offsets, malformed pages, or rows without IDs exit with status 1 before the
output is created. Existing outputs are never overwritten.
