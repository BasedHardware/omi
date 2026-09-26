# Stream goal-list exports to JSON Lines (JSONL)

Use this recipe to stream goal exports to line-delimited JSON (`.jsonl`),
ideal for big data ingestion pipelines, log forwarders, or AI training datasets.
It supports appending new pages while automatically deduplicating existing records
by goal `id`.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Save the following as `goals_to_jsonl.py`:

```python
import json
import sys
from pathlib import Path


def convert(source, destination, append=False):
    """Convert a JSON goal-list export into JSON Lines (.jsonl)."""
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")

    dest_path = Path(destination)
    existing_records = {}

    if append and dest_path.exists():
        for line in dest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and "id" in rec:
                    existing_records[rec["id"]] = rec
            except json.JSONDecodeError:
                continue

    for item in items:
        if not isinstance(item, dict):
            continue
        gid = item.get("id")
        if not gid:
            continue
        record = {
            "id": gid,
            "title": item.get("title", ""),
            "goal_type": item.get("goal_type", ""),
            "current_value": item.get("current_value"),
            "target_value": item.get("target_value"),
            "unit": item.get("unit"),
            "is_active": bool(item.get("is_active", True)),
            "description": item.get("description"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        existing_records[gid] = record

    lines = [json.dumps(r, ensure_ascii=False) for r in existing_records.values()]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")

    if append:
        dest_path.write_bytes(payload)
    else:
        try:
            output = dest_path.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {dest_path}") from None
        try:
            with output:
                output.write(payload)
        except OSError:
            dest_path.unlink(missing_ok=True)
            raise


if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        sys.exit("Usage: python goals_to_jsonl.py INPUT.json OUTPUT.jsonl [--append]")
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    is_append = len(sys.argv) == 4 and sys.argv[3] == "--append"
    try:
        convert(in_file, out_file, append=is_append)
    except Exception as exc:
        sys.exit(f"Error: {exc}")
```

Run the script:

```sh
python goals_to_jsonl.py goals.json goals.jsonl
```

To append another page without duplicates:

```sh
python goals_to_jsonl.py goals_page2.json goals.jsonl --append
```
