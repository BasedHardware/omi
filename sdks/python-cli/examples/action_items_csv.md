# Convert an action-item export to CSV

Use this recipe to review your Omi action items and tasks in spreadsheet
applications such as Microsoft Excel, Google Sheets, or LibreOffice Calc.
It reads saved JSON exports, makes no network requests, and formats tasks into
a structured CSV table. You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the command succeeded before converting the file. To export
additional pages, increase `--offset` by 200 and specify a separate file
(e.g., `page2.json`). The converter accepts multiple input files and
automatically deduplicates items by task ID.

Save the following as `action_items_to_csv.py`:

```python
"""Convert Omi action items JSON exports into a spreadsheet-ready CSV file.

Usage:
    # Basic export from saved JSON file to CSV
    python action_items_to_csv.py action_items.json -o tasks.csv

    # Convert pipeline output from omi CLI
    omi --json action-item list --limit 200 | python action_items_to_csv.py - -o tasks.csv

    # Filter only open action items and format with local timezone offset
    python action_items_to_csv.py --status open --utc-offset +09:00 action_items.json -o open_tasks.csv
    python action_items_to_csv.py --status open --utc-offset=-05:00 action_items.json -o open_tasks.csv

    # Merge multiple page exports into a single deduplicated CSV
    python action_items_to_csv.py page1.json page2.json -o all_tasks.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence
import uuid

COLUMNS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")
DONE_WORDS = {"true", "yes", "1", "done", "completed", "x"}


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Coerces loose types cleanly to strings and guards against CSV formula injection
    by prepending an apostrophe to values beginning with =, +, -, @, or tabs/newlines.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas in spreadsheet software.
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def is_completed(value: Any) -> bool:
    """Normalize completion state handling booleans, numbers, and strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar dates and times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def format_time(dt: Optional[datetime], offset: timedelta) -> str:
    """Format a datetime adjusted by offset into 'YYYY-MM-DD HH:MM:SS' or empty string."""
    if dt is None:
        return ""
    try:
        local_dt = dt + offset
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError):
        return ""


def unwrap_items(raw: Any, source_name: str = "") -> List[Dict[str, Any]]:
    """Unwrap an array of items, an envelope dict, or a single item object."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_items", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return candidate
        if "id" in raw or "description" in raw:
            return [raw]
    raise ValueError(f"{source_name}: expected a JSON array or envelope of action items")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate action items from multiple files or stdin."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            content = sys.stdin.buffer.read()
            source_label = "stdin"
        else:
            source_label = source
            content = Path(source).read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_items(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each action item must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def export_csv(
    items: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    status_filter: str = "all",
) -> str:
    """Format action items dictionary into spreadsheet-ready CSV string."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)

    for item_id, item in items.items():
        completed = is_completed(item.get("completed", False))
        if status_filter == "open" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue

        description = item.get("description")
        due_at = format_time(parse_time(item.get("due_at")), offset)
        created_at = format_time(parse_time(item.get("created_at")), offset)
        updated_at = format_time(parse_time(item.get("updated_at")), offset)
        conversation_id = item.get("conversation_id")

        row = (
            spreadsheet_text(item_id),
            spreadsheet_text(description),
            "TRUE" if completed else "FALSE",
            spreadsheet_text(due_at),
            spreadsheet_text(created_at),
            spreadsheet_text(updated_at),
            spreadsheet_text(conversation_id),
        )
        writer.writerow(row)

    return buffer.getvalue()


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    offset: timedelta = timedelta(0),
    status_filter: str = "all",
    overwrite: bool = False,
) -> int:
    """Load items from sources, format to CSV, and safely write to destination or stdout."""
    items = load(sources)
    csv_text = export_csv(items, offset=offset, status_filter=status_filter)
    payload = csv_text.encode("utf-8-sig")

    status_norm = status_filter.strip().lower() if status_filter else "all"
    row_count = sum(
        1
        for item in items.values()
        if (
            status_norm == "all"
            or (status_norm == "open" and not is_completed(item.get("completed", False)))
            or (status_norm == "completed" and is_completed(item.get("completed", False)))
        )
    )

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return row_count

    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --overwrite to replace)"
            ) from None
        try:
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        # Atomic write to temporary file in same directory with default permissions, then replace destination
        tmp_name = f".tmp_tasks_{uuid.uuid4().hex}.csv"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return row_count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into a spreadsheet-ready CSV file."
    )
    parser.add_argument("inputs", nargs="+", help="One or more action items JSON export files, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Destination CSV file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by completion status (default: all)",
    )
    parser.add_argument(
        "--utc-offset",
        default="",
        help="Local UTC offset, e.g. +09:00 or --utc-offset=-05:00",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    offset = timedelta(0)
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
        except ValueError as exc:
            sys.exit(f"CSV export failed: {exc}")

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            offset=offset,
            status_filter=args.status,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"Exported {count} action items to {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
```

Run the converter:

```sh
# Export directly to a CSV file
python action_items_to_csv.py action_items.json -o tasks.csv

# Or stream directly from omi CLI
omi --json action-item list --limit 200 | python action_items_to_csv.py - -o tasks.csv

# Filter open items with local timezone offset
python action_items_to_csv.py --status open --utc-offset +09:00 action_items.json -o open_tasks.csv
```

Open `tasks.csv` in Microsoft Excel, Google Sheets, or any spreadsheet tool.
The exported CSV includes:
- Fixed columns: `id`, `description`, `completed`, `due_at`, `created_at`, `updated_at`, `conversation_id`.
- UTF-8 with BOM (`utf-8-sig`) encoding for seamless character rendering across Windows, macOS, and Linux spreadsheet importers.
- Spreadsheet formula-injection protection (prepends apostrophe to values starting with `=`, `+`, `-`, `@`, tabs, or newlines).
- Optional `--status` filtering (`all`, `open`, `completed`).
- Local clock formatting with `--utc-offset` (e.g., `+09:00` or `--utc-offset=-05:00`).
- Safe atomic file writes preventing partial file truncation.
