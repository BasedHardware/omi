# Convert a memory-list export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi memories in Excel with real cell types:
`created_at` and `updated_at` become UTC datetime cells you can sort and filter,
boolean flags (`manually_added`, `reviewed`) stay typed, the header row is
frozen, and an AutoFilter is enabled across the table. It reads a saved JSON
export, makes no network requests, and does not require a running server. It
complements [`memories_markdown.md`](memories_markdown.md) and
[`memories_sqlite.md`](memories_sqlite.md); this recipe needs one extra package.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export your memories (up to 500):

```sh
omi --json memory list --limit 500 > memories.json
```

Check that the command succeeded before converting the file. This is one page;
to retrieve more, increase `--offset` by 500 and use a different filename.

Save the following as `memories_to_xlsx.py`:

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FIELDS = (
    "id",
    "category",
    "content",
    "created_at",
    "updated_at",
    "manually_added",
    "reviewed",
    "conversation_id",
)
DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"


def cell_text(value):
    """Render one exported field as text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    Cells are written with an explicit string type, so a value such as
    "=SUM(A1)" or "@mention" stays text and is never evaluated as a formula.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_bool(value):
    """Render a boolean flag.

    Returns a boolean if the value is a bool or case-insensitive string,
    or None if absent.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return bool(value)


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
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "memories"
    header = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")

        created = cell_datetime(item.get("created_at"))
        updated = cell_datetime(item.get("updated_at"))

        row = (
            cell_text(item.get("id")),
            cell_text(item.get("category")),
            cell_text(item.get("content")),
            created,
            updated,
            cell_bool(item.get("manually_added")),
            cell_bool(item.get("reviewed")),
            cell_text(item.get("conversation_id")),
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
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in sheet[get_column_letter(index)])
        sheet.column_dimensions[get_column_letter(index)].width = min(max(len(name), longest) + 2, 70)

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
        sys.exit("Usage: python memories_to_xlsx.py INPUT.json OUTPUT.xlsx")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"XLSX export failed: {exc}")
```

Run the converter:

```sh
python memories_to_xlsx.py memories.json memories.xlsx
```

Open the workbook in Excel, LibreOffice, or Google Sheets. Timestamps are real
datetime cells in UTC, boolean flags are typed, and every text column (including
content and category) is stored with string cell types so characters like `=` or
`-` are never evaluated as spreadsheet formulas. Missing fields become empty
cells; an empty list produces the header row only. The converter refuses to
overwrite an existing destination, and a failed save leaves no partial file
behind. Treat the exported file as private knowledge data. For exact unmodified
values, retain the source JSON.
