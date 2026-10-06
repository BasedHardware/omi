"""Convert an omi-cli memory export to an Excel (.xlsx) workbook.

Reads JSON produced by `omi --json memory list --limit 200` (or piped via stdin),
and generates a structured Excel spreadsheet with native cell types, UTC datetimes,
formula injection defense, frozen headers, and AutoFilter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FIELDS = (
    "id",
    "category",
    "content",
    "tags",
    "visibility",
    "created_at",
    "updated_at",
    "manually_added",
    "reviewed",
)
DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"


def validate_path(path_str: str) -> Path:
    """Validate that path does not attempt path traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: {path_str}")
    return p


def cell_text(value: Any) -> str | None:
    """Render one exported field as text.

    Values are stored with explicit string typing in openpyxl so leading
    '=', '+', '-', or '@' are treated strictly as literal text and never
    evaluated as spreadsheet formulas. Lists (e.g. tags) are joined cleanly.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value: Any) -> datetime | str | None:
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel."""
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


def cell_boolean(value: Any) -> bool | None:
    """Parse a boolean field for Excel."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        val_lower = value.strip().lower()
        if val_lower in ("true", "1", "yes"):
            return True
        if val_lower in ("false", "0", "no"):
            return False
    return None


def convert(source: str | Path, destination: str | Path, overwrite: bool = False) -> int:
    """Convert a memory list JSON export to an Excel (.xlsx) workbook.

    Returns the count of exported records.
    """
    if str(source) == "-":
        raw = sys.stdin.buffer.read()
    else:
        src_path = validate_path(str(source))
        raw = src_path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("memories", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            raise ValueError("Expected a JSON array or envelope object containing 'memories'")
    else:
        raise ValueError("Expected a JSON array or dictionary object")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "memories"

    header = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory record must be a JSON object")

        created_dt = cell_datetime(item.get("created_at"))
        updated_dt = cell_datetime(item.get("updated_at"))

        row = [
            cell_text(item.get("id")),
            cell_text(item.get("category")),
            cell_text(item.get("content")),
            cell_text(item.get("tags")),
            cell_text(item.get("visibility")),
            created_dt,
            updated_dt,
            cell_boolean(item.get("manually_added")),
            cell_boolean(item.get("reviewed")),
        ]
        sheet.append(row)

        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, bool):
                pass
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    if sheet.max_row > 1:
        sheet.auto_filter.ref = sheet.dimensions

    for index, name in enumerate(FIELDS, start=1):
        col_letter = get_column_letter(index)
        longest = max(
            len(str(c.value)) if c.value is not None else 0
            for c in sheet[col_letter]
        )
        sheet.column_dimensions[col_letter].width = min(max(len(name), longest) + 2, 70)

    output_path = validate_path(str(destination))
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file '{output_path}' already exists. Use --overwrite to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.partial")
    try:
        workbook.save(partial)
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise

    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an omi-cli memory export into an Excel (.xlsx) workbook."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' for stdin (default: -)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output Excel workbook file path (.xlsx)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args()

    try:
        count = convert(args.input, args.output, overwrite=args.overwrite)
        print(f"Exported {count} memory record(s) to {args.output}")
    except (OSError, ValueError) as exc:
        sys.exit(f"XLSX export failed: {exc}")


if __name__ == "__main__":
    main()
