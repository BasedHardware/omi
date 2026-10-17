#!/usr/bin/env python3
"""Build a conversation digest (daily totals, categories, longest sessions)."""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def text(value):
    """Render a loosely typed field as one line of text; anything non-null is coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def escape_cell(value):
    """Escape pipe characters so table cells do not break markdown column formatting."""
    return str(value).replace("|", "\\|")


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
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar days."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    return -delta if value[0] == "-" else delta


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if isinstance(items, dict):
            for key in ("conversations", "data", "items"):
                if isinstance(items.get(key), list):
                    items = items[key]
                    break
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


def hours(seconds):
    return f"{seconds / 3600:.1f}"


def digest(conversations, offset):
    per_day = defaultdict(lambda: [0, 0])          # day -> [count, seconds]
    per_category = defaultdict(lambda: [0, 0])
    longest, undated = [], 0
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        if start is None:
            undated += 1
            continue
        seconds = int((end - start).total_seconds()) if end is not None and end >= start else 0
        structured = item.get("structured") or {}
        day = (start + offset).strftime("%Y-%m-%d")
        category = text(structured.get("category")) or "(uncategorised)"
        for bucket in (per_day[day], per_category[category]):
            bucket[0] += 1
            bucket[1] += seconds
        longest.append((seconds, day, text(structured.get("title")) or "(untitled conversation)", item_id))
    total = sum(count for count, _ in per_day.values())
    total_seconds = sum(seconds for _, seconds in per_day.values())
    lines = [
        "# Omi conversation digest",
        "",
        f"Conversations: {total} · Recorded time: {hours(total_seconds)} h · Days with recordings: {len(per_day)}",
    ]
    if undated:
        lines.append(f"Skipped (no start time): {undated}")
    lines += ["", "## Per day", "", "| Day | Conversations | Hours |", "|---|---:|---:|"]
    lines += [f"| {escape_cell(day)} | {count} | {hours(seconds)} |" for day, (count, seconds) in sorted(per_day.items())]
    lines += ["", "## Per category", "", "| Category | Conversations | Hours |", "|---|---:|---:|"]
    by_category = sorted(per_category.items(), key=lambda entry: (-entry[1][0], entry[0]))
    lines += [f"| {escape_cell(category)} | {count} | {hours(seconds)} |" for category, (count, seconds) in by_category]
    lines += ["", "## Longest conversations", ""]
    top = sorted(longest, key=lambda entry: (-entry[0], entry[1], entry[3]))[:5]
    lines += [f"- {hours(seconds)} h · {day} · {title} `{item_id}`" for seconds, day, title, item_id in top] or ["_None._"]
    return "\n".join(lines) + "\n"


def convert(sources, destination, offset):
    payload = digest(load(sources), offset).encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing digest; a failed write leaves no partial file.
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


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    offset = timedelta(0)
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            offset = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"Digest failed: {exc}")
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python conversations_to_digest.py [--utc-offset +09:00] OUTPUT.md INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], offset)
    except (OSError, ValueError) as exc:
        sys.exit(f"Digest failed: {exc}")
    print(f"digest written to {args[0]}")


if __name__ == "__main__":
    main()
