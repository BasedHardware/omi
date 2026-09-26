# Convert a goal-list export to CSV

Use this recipe to review your Omi goals and progress metrics in a spreadsheet.
It reads a saved JSON export, makes no network requests, and processes goals with
complete field and type safety. You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

Export goals (including active and inactive):

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Check that the command succeeded before converting the file.

Save the following as `goals_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "unit",
    "is_active",
    "created_at",
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
        value = str(value).lower()
    elif isinstance(value, (int, float)):
        value = str(value)
    elif not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and prevents spreadsheet formula execution.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal item must be an object")

        values = (
            item.get("id"),
            item.get("title"),
            item.get("goal_type"),
            item.get("current_value"),
            item.get("target_value"),
            item.get("unit"),
            item.get("is_active"),
            item.get("created_at"),
        )
        rows.append([spreadsheet_text(value) for value in values])

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
        sys.exit("Usage: python goals_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
```

Run the converter:

```sh
python goals_to_csv.py goals.json goals.csv
```

Import the result as UTF-8, comma-delimited text in Excel, Numbers, or Google Sheets.
The converter preserves complete metric values, units, qualitative goal titles, and
statuses. Missing values become empty cells; an empty list produces the column header
only. It refuses to overwrite an existing destination file, and a failed write leaves
no partial file behind. For exact unmodified values, retain the source JSON; the CSV
adds an apostrophe to formula-like prefixes to make text interpretation safe.
