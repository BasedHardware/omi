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
    """Raise ValueError if *xlsx_path* is unsafe or points at a non-xlsx file.

    Rules enforced:
    - The path must not contain '..' components (prevents directory traversal).
    - If the file already exists it must be a ZIP-based file (magic-byte check),
      so we never silently clobber an unrelated file.
    """
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
    """Normalize an API timestamp to a naive UTC datetime for a real Excel datetime cell.

    Returns None for missing or unparseable values so the cell stays empty
    rather than carrying a wrong date.
    """
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
    """Return a string that Excel will never evaluate as a formula.

    A cell whose text starts with '=', '+', '-', '@', tab or CR can be executed
    as a formula by spreadsheet software (CSV/Excel injection). We force such
    values onto a string cell with an explicit data type and prefix a quote
    when the value still looks dangerous, so the bytes are shown verbatim.
    """
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
        # A single memory object was exported instead of a list.
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
                    # Force free-text fields onto string cells so a leading
                    # '=' / '+' / '-' / '@' is never evaluated as a formula.
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