# Convert an action-item export to CSV

Use this recipe to review action items and tasks in a spreadsheet. It reads a
saved JSON export, makes no network requests, and stays completely dependency-free
using Python's standard `csv` module. It provides a simple, portable text export
without installing extra packages. You need Python 3.10+ and an authenticated
`omi-cli` for the initial export.

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

FIELDS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and prevents formula execution in Excel/Sheets.
    if clean.startswith(("=", "+", "-", "@")):
        return "'" + clean
    return clean


def to_bool_str(value):
    """Normalize completed status into a standard lowercase boolean string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    if isinstance(value, str):
        return "true" if value.strip().lower() in ("true", "1", "yes", "completed") else "false"
    return "false"


def rows_from(payload):
    """Extract list of action items from array or wrapped object."""
    if isinstance(payload, dict):
        items = payload.get("action_items") or payload.get("items") or payload.get("data")
        if items is None:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(f"expected JSON array or object, got {type(payload).__name__}")
    return items


def convert(source, destination):
    raw_data = json.loads(Path(source).read_bytes())
    items = rows_from(raw_data)

    # Deduplicate items by ID; later occurrences overwrite earlier ones
    deduped = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if not item_id or not isinstance(item_id, str):
            continue
        deduped[item_id] = item

    rows = []
    for item in deduped.values():
        desc = item.get("description") or item.get("text") or item.get("content")
        if not desc:
            continue
        values = (
            item.get("id"),
            desc,
            to_bool_str(item.get("completed")),
            item.get("due_at") or item.get("dueAt"),
            item.get("created_at") or item.get("createdAt"),
            item.get("updated_at") or item.get("updatedAt"),
            item.get("conversation_id") or item.get("conversationId"),
        )
        rows.append([spreadsheet_text(v) for v in values])

    # Format and encode the whole export with UTF-8 BOM so Excel opens it cleanly
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")

    output_path = Path(destination)
    # Exclusive creation protects an existing export from accidental overwrite
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
    print(f"CSV export written to {sys.argv[2]}")
```

Run the converter:

```sh
python action_items_to_csv.py action_items.json action_items.csv
```

Open the CSV file in Excel, Google Sheets, or any tabular data viewer. Encoded
with UTF-8 with BOM (`utf-8-sig`) for automatic character set detection in Excel.
Formula prefixes (`=`, `+`, `-`, `@`) in task descriptions are escaped to prevent
formula execution on spreadsheet import. Missing values produce empty cells, and
the converter refuses to overwrite an existing destination file.
