# Convert an action-items export to CSV

Use this recipe to review action items and task checklists in a spreadsheet. It
reads a saved JSON export, makes no network requests, and requires no external
dependencies. You need Python 3.10+ and an authenticated `omi-cli` for the initial
export.

Export action items to JSON:

```sh
omi --json action-item list --limit 200 > action_items.json
```

Check that the command succeeded before converting the file.

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

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
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
            raise ValueError("Each action item must be an object")
        values = (
            item.get("id"),
            item.get("description"),
            item.get("completed"),
            item.get("due_at"),
            item.get("created_at"),
            item.get("updated_at"),
            item.get("conversation_id"),
        )
        rows.append([spreadsheet_text(value) for value in values])

    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
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

Import the result as UTF-8, comma-delimited text in Excel, Google Sheets, or
another spreadsheet application. The converter preserves complete IDs, quotes,
and embedded newlines. Missing fields become empty cells; an empty list
produces the column header only. It refuses to overwrite an existing
destination, and a failed write leaves no partial file behind. The CSV adds an
apostrophe prefix to formula-like values to make their intended text
interpretation explicit and prevent spreadsheet formula injection.
