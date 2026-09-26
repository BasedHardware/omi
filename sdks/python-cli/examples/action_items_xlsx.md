# Convert an action-item export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi action items and tasks in Excel with real
cell types: `due_at`, `created_at`, and `updated_at` become datetime cells you can
sort and filter chronologically, `completed` is an explicit boolean status, the
header row is frozen, and an AutoFilter is enabled across all columns. It reads a
saved JSON export, makes no network requests, and does not evaluate formulas. It
complements [`action_items_csv.md`](action_items_csv.md), which stays
dependency-free; this recipe needs one extra package (`openpyxl`).

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
    return str(value).strip()


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


def cell_bool(value):
    """Normalize completed status into a standard boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed")
    return False


def rows_from(payload):
    """Extract list of action item objects from array or wrapped object."""
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
        item_id = cell_text(item.get("id"))
        if not item_id:
            continue
        deduped[item_id] = item

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "action_items"
    header = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in deduped.values():
        desc = cell_text(item.get("description") or item.get("text") or item.get("content"))
        if not desc:
            continue
        row = (
            cell_text(item.get("id")),
            desc,
            cell_bool(item.get("completed")),
            cell_datetime(item.get("due_at") or item.get("dueAt")),
            cell_datetime(item.get("created_at") or item.get("createdAt")),
            cell_datetime(item.get("updated_at") or item.get("updatedAt")),
            cell_text(item.get("conversation_id") or item.get("conversationId")),
        )
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, bool):
                cell.data_type = "b"
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, name in enumerate(FIELDS, start=1):
        col_letter = get_column_letter(index)
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in sheet[col_letter])
        sheet.column_dimensions[col_letter].width = min(max(len(name), longest) + 2, 60)

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
    print(f"Excel workbook written to {sys.argv[2]}")
```

Run the converter:

```sh
python action_items_to_xlsx.py action_items.json action_items.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are
real datetime cells in UTC (the header says so), `completed` is a real boolean
column you can filter by `TRUE` or `FALSE`, and descriptions and IDs are treated
as explicit text cells so formulas are never executed and leading zeros are
preserved. Missing timestamps become empty cells; an empty list produces the
header row only. The converter refuses to overwrite an existing destination, and
a failed save leaves no partial file behind.
