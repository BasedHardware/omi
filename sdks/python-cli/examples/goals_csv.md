# Convert a goal-list export to CSV

Use this recipe to review your tracked goals and metrics in a spreadsheet. It
reads a saved JSON export from the `omi` CLI, makes no network requests, and
produces an Excel-compatible CSV file with formula-safe escaping.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list --limit 100 > goals.json
```

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
    "progress_pct",
    "description",
)


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    Avoid treating common formula prefixes as formulas on spreadsheet import.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def calculate_progress(current, target):
    """Calculate progress percentage safely."""
    try:
        if current is not None and target is not None:
            c = float(current)
            t = float(target)
            if t > 0:
                return round((c / t) * 100.0, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return ""


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")
        current_val = item.get("current_value")
        target_val = item.get("target_value")
        progress = calculate_progress(current_val, target_val)

        values = (
            item.get("id"),
            item.get("title"),
            item.get("goal_type"),
            current_val,
            target_val,
            item.get("unit"),
            item.get("is_active"),
            progress,
            item.get("description"),
        )
        rows.append([spreadsheet_text(v) for v in values])

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
    except Exception as exc:
        sys.exit(f"Error: {exc}")
```

Run the script:

```sh
python goals_to_csv.py goals.json goals.csv
```
