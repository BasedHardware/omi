# Convert an action-item export to CSV

Use this recipe to review captured action items, commitments, and tasks in a
spreadsheet (Microsoft Excel, Google Sheets, Apple Numbers) or import them into
project management tools (Jira, Linear, Asana, Trello). It reads a saved JSON
export or standard input (`-`), makes no network requests, and requires no
external packages. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to CSV)

Stream up to 500 action items directly into a `.csv` spreadsheet:

```sh
omi --json action-item list --limit 500 | python action_items_to_csv.py - action_items.csv
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json action-item list --limit 500 > action_items.json
python action_items_to_csv.py action_items.json action_items.csv
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 500 and use a different filename.

### 3. Filter by Status (Pending Tasks Only)

Export only open, pending action items:

```sh
python action_items_to_csv.py action_items.json pending_tasks.csv --status open
```

---

## Converter Script

Save the following as `action_items_to_csv.py`:

```python
import argparse
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split()) if "\n" in value else value
    # Neutralize formula injection prefixes (=, +, -, @) upon spreadsheet opening
    if clean.lstrip().startswith(("=", "+", "-", "@")) or clean.startswith(("\t", "\r", "\n")):
        return "'" + clean
    return clean


def convert(source, destination, status_filter="all", overwrite=False):
    """Convert input action items JSON export or stdin to a destination CSV file."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    items = json.loads(content)
    if isinstance(items, dict) and "action_items" in items:
        items = items["action_items"]
    if not isinstance(items, list):
        raise ValueError("Expected a JSON array of action items from 'omi --json action-item list'")

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

        completed = bool(item.get("completed"))
        if status_filter == "open" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue

        values = (
            item.get("id"),
            item.get("description") or "(untitled task)",
            completed,
            item.get("due_at"),
            item.get("created_at"),
            item.get("updated_at"),
            item.get("conversation_id")
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
    parser = argparse.ArgumentParser(description="Convert Omi action items JSON export to CSV spreadsheet.")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output .csv file.")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status: all (default), open (pending only), or completed."
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists.")

    args = parser.parse_args()

    try:
        count = convert(args.source, args.destination, status_filter=args.status, overwrite=args.overwrite)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully converted {count} action item{'s' if count != 1 else ''} to {args.destination}")
```

---

## Spreadsheet Compatibility & Security

- **UTF-8 with BOM (`utf-8-sig`):** Ensures international characters, accents, and emojis display correctly without garbled symbols in Microsoft Excel, Apple Numbers, and LibreOffice.
- **Formula Injection Mitigation:** Any cell value starting with `= `, `+`, `-`, or `@` is prefixed with an apostrophe (`'`) to neutralize automatic formula execution upon opening.
- **Atomic File Writing:** The CSV payload is fully serialized and encoded in memory before writing to disk, avoiding corrupt or partial files on failure.
