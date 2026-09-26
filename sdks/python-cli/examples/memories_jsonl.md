# Convert a memory export to JSON Lines (JSONL)

Use this recipe to export Omi memories, facts, learnings, and personal knowledge
into standard JSON Lines (`.jsonl`) format. JSON Lines is the standard data format
for fine-tuning LLMs (such as OpenAI, Anthropic, or Llama fine-tuning), training
embedding models, or ingesting memory chunks into vector databases and
Retrieval-Augmented Generation (RAG) pipelines.

It reads one or more saved JSON exports from `omi --json memory list`, normalises
timestamps and tags, deduplicates entries by memory ID, and outputs clean
single-line JSON records formatted for AI dataset ingestion.

It reads saved JSON exports, makes no network requests, and requires only the
Python 3.10+ standard library. You need an authenticated `omi-cli` for the
initial export.

Export the memories you want to convert (up to 200 memories per page):

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. If you have more
memories, retrieve additional pages into separate files (e.g. `memories_200.json`)
using `--offset 200`. The converter accepts multiple files and automatically
deduplicates records by memory ID.

Save the following as `memories_to_jsonl.py`:

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
    """Turn '+09:00' / '-05:30' into a timezone for localized timestamps."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def normalize_tags(value):
    """Normalize tags into a clean list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


def build_record(item, tz):
    """Build a normalized dictionary suitable for JSON Lines AI dataset ingestion."""
    created_dt = parse_time(item.get("created_at") or item.get("createdAt"))
    updated_dt = parse_time(item.get("updated_at") or item.get("updatedAt"))

    created_str = created_dt.astimezone(tz).isoformat() if created_dt else None
    updated_str = updated_dt.astimezone(tz).isoformat() if updated_dt else None

    content = text(item.get("content") or item.get("text") or item.get("description") or item.get("fact"))

    return {
        "id": item.get("id"),
        "content": content,
        "category": text(item.get("category")),
        "visibility": text(item.get("visibility") or item.get("type")),
        "created_at": created_str,
        "updated_at": updated_str,
        "tags": normalize_tags(item.get("tags")),
        "raw": item,
    }


def rows_from(data):
    """Extract list of memory items from parsed JSON object or array."""
    if isinstance(data, dict):
        items = data.get("memories") or data.get("items") or data.get("data")
        if items is None:
            return [data]
        return items if isinstance(items, list) else [items]
    if isinstance(data, list):
        return data
    raise ValueError(f"expected JSON array or object, got {type(data).__name__}")


def load(sources):
    """Load and deduplicate memories across multiple export files."""
    memories = {}
    for source in sources:
        path = Path(source)
        data = json.loads(path.read_bytes())
        items = rows_from(data)
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each memory must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: memory missing valid string id")
            content = item.get("content") or item.get("text") or item.get("description") or item.get("fact")
            if not content:
                continue
            memories[item_id] = item
    return list(memories.values())


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
        sys.exit("Usage: python memories_to_jsonl.py [--utc-offset +09:00] OUTPUT.jsonl INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], tz)
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")
    print(f"JSON Lines memory dataset written to {args[0]}")
```

Run the converter (the output file comes first, then one or more export files):

```sh
python memories_to_jsonl.py memories.jsonl memories_0.json memories_200.json
```

Or convert with local time zone offsets:

```sh
python memories_to_jsonl.py --utc-offset -05:00 memories.jsonl memories_0.json
```

## Dataset Format

Each row in the resulting `.jsonl` file is a complete JSON object with the following schema:

```json
{
  "id": "mem_98765",
  "content": "Prefers lightweight ergonomic keyboards with mechanical brown switches.",
  "category": "preferences",
  "visibility": "private",
  "created_at": "2026-09-24T18:15:00+00:00",
  "updated_at": "2026-09-24T18:20:00+00:00",
  "tags": ["hardware", "ergonomics", "desk-setup"],
  "raw": {
    "id": "mem_98765",
    "content": "Prefers lightweight ergonomic keyboards with mechanical brown switches.",
    "category": "preferences",
    "visibility": "private",
    "created_at": "2026-09-24T18:15:00Z",
    "updated_at": "2026-09-24T18:20:00Z",
    "tags": ["hardware", "ergonomics", "desk-setup"]
  }
}
```

The output file is written with exclusive creation (`xb`), so it refuses to overwrite existing datasets.
