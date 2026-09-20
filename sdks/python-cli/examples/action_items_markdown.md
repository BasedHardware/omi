# Export action items to an Obsidian Tasks checklist

This recipe turns one or more saved `omi --json action-item list` pages into a
single Markdown checklist. It makes no network requests and uses only the
Python standard library. Later pages win when the same action-item `id` occurs
more than once, which makes it safe to refresh an overlapping page.

Export one or more pages and write the checklist:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
omi --json action-item list --limit 200 --offset 200 > action_items_200.json
python action_items_to_markdown.py action_items_0.json action_items_200.json \
  --output ActionItems.md
```

Save the following as `action_items_to_markdown.py`:

```python
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


UTC = timezone.utc
_WRAPPER_KEYS = ("action_items", "items", "data")


def read_json(source):
    """Read a UTF-8 JSON page from a path or stdin."""
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
            raise ValueError(f"{source}: expected a JSON array of action items")
    else:
        raise ValueError(f"{source}: expected a JSON array of action items")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: item {index} must be an object")
    return items


def text(value):
    """Render loosely typed API data without losing non-string values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def parse_timestamp(value):
    """Parse an ISO-8601 value and normalise it to UTC, or return None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def completed(value):
    """Only a real JSON boolean can mark an item complete."""
    return value is True


def safe_line(value):
    """Keep one source description on one checklist line."""
    rendered = text(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    rendered = re.sub(r"\s+", " ", rendered).strip()
    if not rendered:
        rendered = "(no description)"
    return rendered.replace("`", "\\`")


def load_items(sources):
    """Merge pages by id; the last occurrence is authoritative for this export."""
    merged = {}
    for source in sources:
        for item in page_items(source):
            item_id = item.get("id")
            if item_id is None or not text(item_id).strip():
                raise ValueError(f"{source}: every action item must have a non-empty id")
            merged[text(item_id)] = item
    return list(merged.items())


def sort_items(items):
    def key(pair):
        item_id, item = pair
        due = parse_timestamp(item.get("due_at"))
        created = parse_timestamp(item.get("created_at")) or datetime.min.replace(tzinfo=UTC)
        # Due items are earliest first. Undated items follow, newest-created first.
        if due is not None:
            return (0, due, -created.timestamp(), item_id)
        return (1, datetime.max.replace(tzinfo=UTC), -created.timestamp(), item_id)

    return sorted(items, key=key)


def date_label(value, prefix):
    parsed = parse_timestamp(value)
    return f"{prefix} {parsed.date().isoformat()}" if parsed else None


def render(items):
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    completed_count = sum(completed(item.get("completed")) for _, item in items)
    lines = [
        "---",
        "type: omi-action-items",
        f"total: {len(items)}",
        f"open: {len(items) - completed_count}",
        f"completed: {completed_count}",
        f'exported_at: "{now}"',
        "---",
        "",
        "# Omi Action Items",
        "",
    ]
    if not items:
        lines.append("- No action items found.")
        return "\n".join(lines) + "\n"

    for item_id, item in sort_items(items):
        marker = "x" if completed(item.get("completed")) else " "
        metadata = []
        due = date_label(item.get("due_at"), "📅")
        finished = date_label(item.get("completed_at"), "✅")
        if due:
            metadata.append(due)
        if finished:
            metadata.append(finished)
        metadata.append(f"`omi:{item_id}`")
        suffix = " · ".join(metadata)
        lines.append(f"- [{marker}] {safe_line(item.get('description'))} {suffix}")
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
    parser.add_argument("-o", "--output", required=True, help="new Markdown output path")
    args = parser.parse_args(argv)
    if args.inputs.count("-") > 1:
        parser.error("stdin may be used for only one input page")
    try:
        write_exclusive(args.output, render(load_items(args.inputs)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"action-item export failed: {exc}\n")


if __name__ == "__main__":
    main()
```

The output has YAML counts and an export timestamp. Each checklist line ends
with an `` `omi:<id>` `` marker, due dates are rendered as `📅 YYYY-MM-DD`, and
completed timestamps as `✅ YYYY-MM-DD`. Due dates are normalised to UTC before
the date is chosen; an undated item is placed after dated items and sorted by
newest `created_at`. Descriptions with newlines are kept on one checklist line.

The converter validates all pages before creating the destination, refuses to
overwrite an existing file, and removes a newly-created partial file if the
write fails. A malformed page, non-array input, item without an id, or invalid
item shape exits with status 1 without replacing an existing export.
