# Convert an action-item export to CSV

Use this recipe to review your Omi tasks and action items in a spreadsheet. It
reads a saved JSON export, makes **no network requests**, and turns each item
into a row. You need Python 3.10+ and an authenticated `omi-cli` for the initial
export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset` by
200 and use a different filename; run the converter on each page, or concatenate
the arrays first. Changes to the account between requests can affect offset
pagination; this recipe does not promise a consistent snapshot.

Save the following as `action_items_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    where the CLI models it as text. One odd row must not destroy a whole
    export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid a spreadsheet treating common formula prefixes as formulas on import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def completed_flag(value):
    """Normalise a loosely typed `completed` field to TRUE/FALSE for spreadsheets."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return "TRUE" if value.strip().lower() in ("true", "1", "yes") else "FALSE"
    return "FALSE"


def items_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    data = json.loads(content)
    if isinstance(data, dict):
        data = (
            data.get("action_items")
            or data.get("items")
            or data.get("data")
            or [data]
        )
    if not isinstance(data, list):
        raise ValueError(f"{source}: expected a JSON array from omi --json action-item list")
    return data


def rows_for(data):
    rows = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        rows.append([
            spreadsheet_text(item.get("id")),
            spreadsheet_text(item.get("description") or item.get("title")),
            completed_flag(item.get("completed")),
            spreadsheet_text(item.get("due_at")),
            spreadsheet_text(item.get("created_at")),
            spreadsheet_text(item.get("updated_at")),
            spreadsheet_text(item.get("conversation_id")),
        ])
    return rows


def convert(source, destination):
    data = items_from(source)          # parse fully before writing anything
    rows = rows_for(data)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation protects an existing export from being clobbered.
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
another spreadsheet application. The converter preserves complete IDs, accents,
quoted text, and embedded newlines; `completed` becomes `TRUE`/`FALSE` so
spreadsheets treat it as a boolean rather than text; missing fields become empty
cells and an empty list produces the column header only. It refuses to overwrite
an existing destination, and a failed write leaves no partial file behind. Treat
the exported file as private task data. For exact, unmodified values retain the
source JSON; the CSV prefixes an apostrophe to common formula-like values to make
their intended-text interpretation explicit.
