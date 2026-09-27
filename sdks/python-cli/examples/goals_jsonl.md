# Stream goal-list exports to JSON Lines (JSONL)

Use this recipe to stream goal exports to line-delimited JSON (`.jsonl`),
ideal for big data ingestion pipelines, log forwarders, or AI training datasets.
It supports appending subsequent exports while automatically deduplicating existing records
by goal `id` and normalizing schemas to match `GoalResponse`.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## Exporting Goals

Export your active goals (the CLI supports `--limit` from 1 to 100):

```sh
omi --json goal list --limit 100 > active_goals.json
```

To include inactive or completed goals:

```sh
omi --json goal list --limit 100 --include-inactive > all_goals.json
```

## Python Conversion Script

Save the following as `goals_to_jsonl.py`:

```python
import json
import os
from pathlib import Path
import sys


def convert(source, destination, append=False):
    """Convert a JSON goal-list export into line-delimited JSON Lines (.jsonl)."""
    source_path = Path(source)
    dest_path = Path(destination).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    raw_data = source_path.read_bytes()
    try:
        items = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in source file: {exc}") from exc

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array of goals from 'omi --json goal list'")

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

    # Merge and normalize incoming items according to GoalResponse schema
    for item in items:
        if not isinstance(item, dict):
            continue
        gid = item.get("id") or item.get("goal_id")
        if not gid:
            continue

        record = {
            "id": gid,
            "goal_id": item.get("goal_id", gid),
            "title": item.get("title", ""),
            "desired_outcome": item.get("desired_outcome", ""),
            "why_it_matters": item.get("why_it_matters"),
            "success_criteria": item.get("success_criteria") or [],
            "horizon_at": item.get("horizon_at"),
            "status": item.get("status", ""),
            "focus_rank": item.get("focus_rank"),
            "metric": item.get("metric"),
            "source": item.get("source", ""),
            "goal_type": item.get("goal_type", ""),
            "target_value": item.get("target_value"),
            "current_value": item.get("current_value"),
            "min_value": item.get("min_value"),
            "max_value": item.get("max_value"),
            "unit": item.get("unit"),
            "is_active": bool(item.get("is_active", True)),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        existing_records[gid] = record

    lines = [json.dumps(r, ensure_ascii=False) for r in existing_records.values()]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")

    if not append and dest_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {dest_path}")

    # Atomic write via temporary file in the same directory and atomic replace
    temp_file = dest_path.with_name(f".{dest_path.name}.tmp.{os.getpid()}")
    try:
        with temp_file.open("wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, dest_path)
    except Exception:
        temp_file.unlink(missing_ok=True)
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

## Running the Script

Convert your initial export:

```sh
python goals_to_jsonl.py active_goals.json goals.jsonl
```

To merge another export (such as including inactive goals or scheduled snapshot backups) without duplicate records:

```sh
python goals_to_jsonl.py all_goals.json goals.jsonl --append
```

## Safety and Atomicity

- **Atomic Writes:** Output is buffered to a temporary file in the destination directory and committed atomically via `os.replace`, avoiding corrupted partial writes.
- **Accidental Overwrite Protection:** Running without `--append` against an existing file raises a `FileExistsError` to prevent accidental data loss.
- **Deduplication:** Subsequent runs with `--append` update existing goals by `id` while inserting new ones.
