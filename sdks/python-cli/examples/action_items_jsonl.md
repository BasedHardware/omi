# Convert action-item exports to JSON Lines (.jsonl)

Use this recipe to convert Omi action items and task exports into JSON Lines
(`.jsonl`) format. Line-delimited JSON is the standard streaming data format
for AI task agents, fine-tuning datasets, embedding models, and data pipelines
without having to load large JSON arrays entirely into memory.

It reads saved JSON exports, makes no network requests, and requires only the
Python 3.10+ standard library. You need an authenticated `omi-cli` for the
initial export.

Export up to 200 action items per page:

```sh
omi --json action-item list --limit 200 --offset 0 > page1.json
```

Check that the command succeeded before converting the file. If you have more
tasks, retrieve additional pages into separate files (e.g. `page2.json`)
using `--offset 200`. The converter accepts multiple files and automatically
deduplicates records by action item ID.

Save the following as `action_items_to_jsonl.py`:

```python
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def text(value):
    """Render a loosely typed field as clean text; anything non-null is coerced."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    return clean if clean else None


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timezone for localized timestamps."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def to_bool(value):
    """Normalize completed status into a standard boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def compute_status(completed, due_dt):
    """Compute task status: 'completed', 'overdue', or 'pending'."""
    if completed:
        return "completed"
    if due_dt and due_dt < datetime.now(timezone.utc):
        return "overdue"
    return "pending"


def build_record(item, tz):
    """Build a normalized dictionary suitable for JSON Lines AI dataset ingestion."""
    created_dt = parse_time(item.get("created_at"))
    updated_dt = parse_time(item.get("updated_at"))
    due_dt = parse_time(item.get("due_at"))

    completed = to_bool(item.get("completed"))
    status = compute_status(completed, due_dt)

    description = item.get("description") or item.get("title") or item.get("content") or ""

    return {
        "id": item.get("id"),
        "description": text(description),
        "completed": completed,
        "status": status,
        "due_at": due_dt.astimezone(tz).isoformat() if due_dt else None,
        "created_at": created_dt.astimezone(tz).isoformat() if created_dt else None,
        "updated_at": updated_dt.astimezone(tz).isoformat() if updated_dt else None,
        "conversation_id": text(item.get("conversation_id")),
        "raw": item,
    }


def load(sources):
    """Load and deduplicate action items across multiple export files."""
    items_by_id = {}
    for source in sources:
        content = Path(source).read_bytes().decode("utf-8-sig")
        data = json.loads(content)
        if isinstance(data, dict):
            raw_items = (
                data.get("action_items")
                or data.get("items")
                or data.get("data")
                or [data]
            )
        else:
            raw_items = data

        if not isinstance(raw_items, list):
            raise ValueError(f"{source}: expected a JSON array or object containing action items")

        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each action item must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError(f"{source}: action item missing valid string id")
            clean_id = item_id.strip()
            existing = items_by_id.get(clean_id)
            if existing is not None:
                new_updated = parse_time(item.get("updated_at") or item.get("created_at"))
                existing_updated = parse_time(existing.get("updated_at") or existing.get("created_at"))
                if new_updated and existing_updated:
                    if new_updated > existing_updated:
                        items_by_id[clean_id] = item
                elif new_updated and not existing_updated:
                    items_by_id[clean_id] = item
            else:
                items_by_id[clean_id] = item
    return list(items_by_id.values())


def convert(sources, destination, tz):
    """Convert source exports into a JSON Lines dataset."""
    items = load(sources)
    buffer = io.StringIO()
    for item in items:
        record = build_record(item, tz)
        line = json.dumps(record, ensure_ascii=False)
        buffer.write(line + "\n")

    payload = buffer.getvalue().encode("utf-8")
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


if __name__ == "__main__":
    args = sys.argv[1:]
    tz = timezone.utc
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            tz = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"JSONL export failed: {exc}")
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python action_items_to_jsonl.py [--utc-offset +09:00] OUTPUT.jsonl INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], tz)
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")
    print(f"JSON Lines dataset written to {args[0]}")
```

Run the converter (the output file comes first, then one or more export files):

```sh
python action_items_to_jsonl.py action_items.jsonl page1.json page2.json
```

Or convert with local time zone offsets for calendar and deadline analysis:

```sh
python action_items_to_jsonl.py --utc-offset -05:00 action_items.jsonl action_items.json
```

## Dataset Format

Each row in the resulting `.jsonl` file is a complete JSON object with the following schema:

```json
{
  "id": "act_67890",
  "description": "Finalize Q4 roadmap slide deck by Friday",
  "completed": false,
  "status": "pending",
  "due_at": "2026-10-02T17:00:00-05:00",
  "created_at": "2026-09-24T14:35:00-05:00",
  "updated_at": "2026-09-24T14:35:00-05:00",
  "conversation_id": "conv_12345",
  "raw": {
    "id": "act_67890",
    "description": "Finalize Q4 roadmap slide deck by Friday",
    "completed": false,
    "due_at": "2026-10-02T22:00:00Z",
    "created_at": "2026-09-24T19:35:00Z",
    "updated_at": "2026-09-24T19:35:00Z",
    "conversation_id": "conv_12345"
  }
}
```

The output file is written with exclusive creation (`xb`), so it refuses to overwrite existing datasets.
