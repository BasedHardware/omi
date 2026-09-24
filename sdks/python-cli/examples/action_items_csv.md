# Convert an action-item export to CSV

Use this recipe to review your Omi action items and tasks in a spreadsheet (Google
Sheets, Microsoft Excel, Apple Numbers). It reads saved JSON exports, makes no network
requests, and outputs UTF-8 with BOM (`utf-8-sig`) so desktop spreadsheet apps parse
accents, unicode, and commas without formatting issues. You need Python 3.10+ and
an authenticated `omi-cli` for the initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `action_items_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = (
    "id",
    "description",
    "completed",
    "due_at",
    "created_at",
    "updated_at",
    "conversation_id",
)


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    Coerces non-null values safely to strings and escapes common formula
    prefixes (=, +, -, @) to prevent CSV injection vulnerabilities.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and prevents formula execution in Excel/Sheets.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def boolean_text(value):
    """Render completed status as clean boolean string ('true' or 'false')."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    if isinstance(value, str):
        return "true" if value.strip().lower() in ("true", "1", "yes") else "false"
    return "false"


def convert(source, destination):
    """Convert an Omi action items JSON export to a CSV file."""
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("action_items")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each action item must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: action item is missing an id")

        description = item.get("description") or item.get("title") or ""
        completed = boolean_text(item.get("completed"))
        values = (
            item_id,
            description,
            completed,
            item.get("due_at"),
            item.get("created_at"),
            item.get("updated_at"),
            item.get("conversation_id"),
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
    if len(sys.argv) != 3:
        sys.exit("Usage: python action_items_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
```

Run the converter:

```sh
python action_items_to_csv.py action_items.json action_items.csv
```

Import the result as UTF-8, comma-delimited text in Excel, Google Sheets, or Apple
Numbers. The converter preserves complete IDs, dates, and multi-line task descriptions.
Missing fields become empty cells. It refuses to overwrite an existing destination to
protect prior exports, and a failed write leaves no partial file behind. It escapes
formula trigger characters (`=`, `+`, `-`, `@`) with a leading apostrophe to guard
against spreadsheet CSV formula injection.
