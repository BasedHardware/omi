# Convert an action-item export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi action items and tasks in Excel with real cell
types: `due_at`, `created_at`, and `updated_at` become datetime cells you can sort and
filter, `completed` becomes a boolean checkbox/status, the header row is frozen,
and an AutoFilter is enabled. It reads a saved JSON export, makes no network
requests, and requires one extra package. It complements
[`action_items_csv.md`](action_items_csv.md), which stays dependency-free.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `action_items_to_xlsx.py`:

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FIELDS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")
DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"


def cell_text(value):
    """Render one exported field as text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    Cells are written with an explicit string type, so a value such as
    "=SUM(A1)" stays text and is never evaluated as a formula.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value):
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel.

    Excel cells cannot carry a timezone, so every offset is converted to UTC
    and the header says so. Anything that is not a parseable timestamp is
    kept as text instead of being dropped.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return cell_text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def convert(source, destination):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = items.get("action_items") or items.get("items") or items.get("data") or [items]
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "action_items"
    header = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        
        completed_val = item.get("completed")
        if completed_val is not None and not isinstance(completed_val, bool):
            completed_val = bool(completed_val)

        row = (
            cell_text(item.get("id")),
            cell_text(item.get("description")),
            completed_val,
            cell_datetime(item.get("due_at")),
            cell_datetime(item.get("created_at")),
            cell_datetime(item.get("updated_at")),
            cell_text(item.get("conversation_id")),
        )
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, name in enumerate(FIELDS, start=1):
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in sheet[get_column_letter(index)])
        sheet.column_dimensions[get_column_letter(index)].width = min(max(len(name), longest) + 2, 60)

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")
    # Write next to the destination and rename, so a failed save cannot leave a
    # truncated workbook behind for the next run.
    partial = output_path.with_name(output_path.name + ".partial")
    try:
        workbook.save(partial)
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python action_items_to_xlsx.py INPUT.json OUTPUT.xlsx")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"XLSX export failed: {exc}")
```

Run the converter:

```sh
python action_items_to_xlsx.py action_items.json action_items.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are
real datetime cells in UTC (the header says so), `completed` is a boolean value,
and every other column is text, so IDs keep leading zeros and descriptions that
look like formulas are never evaluated. Missing fields become empty cells; an
empty list produces the header row only. The converter refuses to overwrite an
existing destination, and a failed save leaves no partial file behind. Treat
the exported file as private personal data. For exact unmodified values,
retain the source JSON.
