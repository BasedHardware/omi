# Convert a memory-list export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi memories in Excel with real cell types:
`created_at` / `updated_at` become datetime cells you can sort and filter,
`manually_added` / `reviewed` stay booleans, free-text columns are forced onto
string cells so a leading `=`, `+`, `-` or `@` is never evaluated as a formula,
the header row is frozen, an AutoFilter is enabled, and column widths are
scaled for readability. It reads a saved JSON export, makes no network
requests, and writes the workbook atomically.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export your memories:

```sh
omi --json memory list --limit 500 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by the limit you used and write to a different filename. Changes to the account
between requests can affect offset pagination; this recipe does not promise a
consistent snapshot.

Save the following as `memories_to_xlsx.py`:

```python
"""Convert an Omi memory-list export to an Excel workbook (.xlsx).

See memories_xlsx.md for the full recipe.

Usage:
    omi --json memory list --limit 500 > memories.json
    python memories_to_xlsx.py memories.json omi_memories.xlsx
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

_XLSX_MAGIC = b"PK\x03\x04"

COLUMNS = [
    ("id", 36),
    ("content", 60),
    ("category", 18),
    ("created_at", 22),
    ("updated_at", 22),
    ("manually_added", 16),
    ("reviewed", 12),
    ("source", 20),
]

DATETIME_COLUMNS = {"created_at", "updated_at"}
BOOLEAN_COLUMNS = {"manually_added", "reviewed"}

# Leading characters Excel / LibreOffice may evaluate as a formula.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def validate_xlsx_path(xlsx_path: str) -> None:
    """Raise ValueError if *xlsx_path* is unsafe or points at a non-xlsx file."""
    p = Path(xlsx_path)
    if ".." in p.parts:
        raise ValueError(
            f"Output path {xlsx_path!r} contains '..'; refusing to write outside the intended directory."
        )
    if p.exists():
        try:
            with p.open("rb") as fh:
                header = fh.read(len(_XLSX_MAGIC))
        except OSError as exc:
            raise ValueError(f"Cannot read existing file {xlsx_path!r}") from exc
        if header != _XLSX_MAGIC:
            raise ValueError(
                f"{xlsx_path!r} already exists but is not an xlsx workbook; refusing to overwrite it."
            )


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def utc_stamp(value):
    """Normalize an API timestamp to a naive UTC datetime for a real Excel datetime cell."""
    if not isinstance(value, str) or not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def boolean_flag(value):
    """Coerce an API flag to a real bool so the cell is a boolean, not text."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def safe_string(value):
    """Return a string that Excel will never evaluate as a formula."""
    if value is None:
        return None
    s = value if isinstance(value, str) else text(value)
    if s is None:
        return None
    if s.startswith(_FORMULA_TRIGGERS):
        return "'" + s
    return s


def load(payload):
    """Accept the CLI JSON export and return the list of memory dicts."""
    if isinstance(payload, dict):
        for key in ("memories", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
        return [payload]
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    return []


def write_workbook(memories, xlsx_path):
    """Write *memories* to *xlsx_path* atomically; returns the row count written."""
    validate_xlsx_path(xlsx_path)
    target = Path(xlsx_path)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "memories"

    for column_index, (name, _width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=name)
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"

    for row_index, memory in enumerate(memories, start=2):
        for column_index, (name, _width) in enumerate(COLUMNS, start=1):
            raw = memory.get(name)
            if name in DATETIME_COLUMNS:
                value = utc_stamp(raw)
            elif name in BOOLEAN_COLUMNS:
                value = boolean_flag(raw)
            else:
                value = safe_string(raw)
            cell = sheet.cell(row=row_index, column=column_index)
            if value is not None:
                cell.value = value
                if name not in DATETIME_COLUMNS and name not in BOOLEAN_COLUMNS:
                    cell.data_type = "s"

    if memories:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(memories) + 1}"

    for column_index, (_name, width) in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width

    tmp_path = target.with_name(target.name + ".partial")
    workbook.save(tmp_path)
    tmp_path.replace(target)
    return len(memories)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert an Omi memory-list export to an Excel workbook."
    )
    parser.add_argument("json_path", help="Path to the saved 'omi --json memory list' export.")
    parser.add_argument("xlsx_path", help="Path of the .xlsx workbook to write.")
    args = parser.parse_args(argv)

    try:
        with open(args.json_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read {args.json_path!r}: {exc}", file=sys.stderr)
        return 1

    memories = load(payload)
    try:
        count = write_workbook(memories, args.xlsx_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {count} memories to {args.xlsx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```sh
python memories_to_xlsx.py memories.json omi_memories.xlsx
```

## Notes

- **Datetime, not text.** `created_at` and `updated_at` are normalized to UTC
  and written as real datetime cells, so Excel sorts and filters them
  chronologically. Unparseable or missing timestamps stay empty rather than
  writing a wrong date.
- **Booleans stay booleans.** `manually_added` and `reviewed` are coerced from
  `true` / `"yes"` / `1` style values into real boolean cells.
- **Formula injection defense.** Memory content is attacker-influenced: a
  memory whose text starts with `=`, `+`, `-` or `@` could be executed as a
  formula by spreadsheet software. Such values are written to an explicit
  string cell (`cell.data_type = "s"`), which keeps the bytes verbatim.
- **Atomic writes.** The workbook is saved to `<name>.partial` and then moved
  into place, so a crash mid-write cannot leave a half-written file at the
  destination.
- **Refuses unsafe output.** A path containing `..` is rejected, and an
  existing file that is not a ZIP-based workbook is never overwritten.
- **Empty exports are fine.** With no memories you still get a header-only
  workbook, and no AutoFilter range is set.
- The script only reads the JSON file you pass; it makes no network requests
  and never reads your credentials.

## Tests

The repository ships hermetic tests for this recipe:

```sh
python -m pytest tests/test_memories_to_xlsx.py -v
```

They cover timestamp normalization, boolean coercion, formula-injection
neutralization, path validation, real cell types, AutoFilter and column
widths, empty exports, and that no `.partial` file is left behind.
