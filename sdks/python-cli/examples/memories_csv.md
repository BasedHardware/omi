# Convert a memory-list export to CSV

Use this recipe to review captured memories in a spreadsheet. It reads a
saved JSON export, makes no network requests, and produces tabular output for
Excel, Google Sheets, Numbers, or pandas. It is stdlib-only (the `csv`
module); no third-party dependencies. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

Export a page of memories:

```sh
omi --json memory list --limit 100 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. `omi memory list` returns only its default page
(25 items) unless you pass `--limit`; to page through larger accounts, increase
`--offset` and use a different filename. Changes to the account between
requests can affect offset pagination; this recipe does not promise a
consistent snapshot.

Save the following as `memories_to_csv.py`:

```python
import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


COLUMNS = ["id", "content", "category", "visibility", "tags", "created_at"]

# Characters that can turn a spreadsheet cell into a formula / command.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r", "\n")


def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def sanitize_cell(value: str) -> str:
    if value.lstrip(" \t\r\n").startswith(_FORMULA_LEAD):
        return "'" + value
    return value


def _tags_str(item: Dict[str, Any]) -> str:
    tags = item.get("tags")
    if isinstance(tags, list):
        return ";".join(str(t) for t in tags if t)
    return ""


def format_row(item: Dict[str, Any]) -> Dict[str, str]:
    content = str(item.get("content") or "").strip()
    created_dt = parse_datetime(item.get("created_at"))
    return {
        "id": sanitize_cell(str(item.get("id") or "")),
        "content": sanitize_cell(content),
        "category": sanitize_cell(str(item.get("category") or "")),
        "visibility": sanitize_cell(str(item.get("visibility") or "")),
        "tags": sanitize_cell(_tags_str(item)),
        "created_at": created_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if created_dt else "",
    }


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("memories", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("content", "category", "id", "created_at")):
            return [data]
        return []
    return []


def filter_memories(
    items: List[Dict[str, Any]],
    category_filter: Optional[str] = None,
    visibility_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    filtered = items
    if category_filter:
        target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
        filtered = [it for it in filtered if str(it.get("category") or "").strip().lower() in target_cats]
    if visibility_filter:
        target_vis = visibility_filter.strip().lower()
        if target_vis in {"public", "private"}:
            filtered = [it for it in filtered if str(it.get("visibility") or "").strip().lower() == target_vis]
    return filtered


def memories_to_csv(items: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for it in items:
        writer.writerow(format_row(it))
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Omi memories JSON exports to a CSV spreadsheet.")
    parser.add_argument("input", help="Path to JSON file containing memories, or '-' to read from stdin.")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Path to output CSV file. Defaults to stdout if omitted.")
    parser.add_argument("--category", "-c", type=str, default=None, help="Filter by category (comma-separated list, e.g. 'work,skills,learnings').")
    parser.add_argument("--visibility", type=str, choices=["all", "public", "private"], default="all", help="Filter by visibility (default: all).")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            input_path = Path(args.input)
            if not input_path.exists():
                sys.stderr.write(f"Error: Input file does not exist: {args.input}\n")
                return 1
            raw_data = input_path.read_bytes().decode("utf-8-sig", errors="replace")
        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1
        payload = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    if not isinstance(payload, (list, dict)):
        sys.stderr.write("Error: Expected a JSON array of memories or object containing 'memories'.\n")
        return 1

    items = filter_memories(
        extract_memories(payload),
        category_filter=args.category,
        visibility_filter=args.visibility if args.visibility != "all" else None,
    )
    csv_doc = memories_to_csv(items)

    try:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(csv_doc, encoding="utf-8")
            sys.stderr.write(f"Successfully exported {len(items)} memory/memories to {args.output}\n")
        else:
            try:
                sys.stdout.write(csv_doc)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(csv_doc.encode("utf-8", errors="replace"))
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error during export: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

Run the converter:

```sh
python memories_to_csv.py memories.json --output memories.csv
```

Or pipe directly from the CLI to a file:

```sh
omi --json memory list --limit 100 | python memories_to_csv.py - --output memories.csv
```

Filter by category and visibility:

```sh
omi --json memory list --limit 100 | python memories_to_csv.py - --category work,learnings --visibility private
```

Import the result as UTF-8, comma-delimited text in Excel or another
spreadsheet application. The converter preserves complete IDs, accents, quoted
text, and embedded newlines. Missing fields become empty cells; an empty list
produces the column header only. It normalizes timestamps to UTC
(`%Y-%m-%dT%H:%M:%SZ`) and leaves unparseable dates blank. Treat the exported
file as private memory data. For exact unmodified values, retain the source
JSON; the CSV adds an apostrophe to common formula-like values (`=`, `+`, `-`,
`@`, tab, CR, LF) to make their intended text interpretation explicit.
