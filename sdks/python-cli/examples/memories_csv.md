# Convert a memory-list export to CSV

Use this recipe to review captured memories, facts, learnings, and user preferences
in a spreadsheet (Microsoft Excel, Google Sheets, Apple Numbers). It reads a
saved JSON export or standard input (`-`), makes no network requests, and does
not require external packages. You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to CSV)

Stream up to 200 memories directly into a `.csv` spreadsheet:

```sh
omi --json memory list --limit 200 | python memories_to_csv.py - memories.csv
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
python memories_to_csv.py memories.json memories.csv
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename.

### 3. Filter by Category

Export only specific categories of memories (e.g. work and learnings):

```sh
python memories_to_csv.py memories.json work_memories.csv --category work,learnings
```

---

## Converter Script

Save the following as `memories_to_csv.py`:

```python
import argparse
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "category", "content", "created_at", "updated_at", "source", "tags")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    elif not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
    # Flatten linebreaks to keep one clean row per memory in spreadsheet tables
    clean = " ".join(value.split()) if "\n" in value else value
    # Neutralize formula injection prefixes (=, +, -, @) upon spreadsheet opening
    if clean.lstrip().startswith(("=", "+", "-", "@")) or clean.startswith(("\t", "\r", "\n")):
        return "'" + clean
    return clean


def convert(source, destination, categories=None, overwrite=False):
    """Convert input memories JSON export or stdin to a destination CSV file."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    items = json.loads(content)
    if isinstance(items, dict) and "memories" in items:
        items = items["memories"]
    if not isinstance(items, list):
        raise ValueError("Expected a JSON array of memories from 'omi --json memory list'")

    category_filter = set(categories) if categories else None

    rows = []
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)

        cat = item.get("category")
        if category_filter and cat not in category_filter:
            continue

        values = (
            item.get("id"),
            item.get("category"),
            item.get("content") or item.get("text") or item.get("memory") or "",
            item.get("created_at"),
            item.get("updated_at"),
            item.get("source"),
            item.get("tags")
        )
        rows.append([spreadsheet_text(v) for v in values])

    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")

    output_path = Path(destination)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to replace)")

    try:
        output_path.write_bytes(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise

    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi memory list JSON export to CSV spreadsheet.")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output .csv file.")
    parser.add_argument(
        "--category",
        help="Optional comma-separated categories to include (e.g. 'work,learnings')."
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists.")

    args = parser.parse_args()
    cats = [c.strip() for c in args.category.split(",") if c.strip()] if args.category else None

    try:
        count = convert(args.source, args.destination, categories=cats, overwrite=args.overwrite)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully converted {count} memor{'ies' if count != 1 else 'y'} to {args.destination}")
```

---

## Spreadsheet Compatibility & Security

- **UTF-8 with BOM (`utf-8-sig`):** Ensures international characters, accents, and emojis display correctly without garbled symbols in Microsoft Excel, Apple Numbers, and LibreOffice.
- **Formula Injection Mitigation:** Any cell value starting with `= `, `+`, `-`, or `@` is prefixed with an apostrophe (`'`) to neutralize automatic formula execution upon opening.
- **Atomic File Writing:** The CSV payload is fully serialized and encoded in memory before writing to disk, avoiding corrupt or partial files on failure.
