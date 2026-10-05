#!/usr/bin/env python3
"""Convert an Omi action-items JSON export to an Excel workbook (.xlsx).

Creates a formatted spreadsheet with native datetime cells, frozen headers,
autofilters, auto-fit columns, and explicit string typing to prevent formula
injection and retain formatting.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

FIELDS = (
    "id",
    "description",
    "completed",
    "due_at",
    "created_at",
    "updated_at",
    "conversation_id",
)

DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"


def cell_text(value: Any) -> Optional[str]:
    """Render one exported field as text.

    Coerces dicts/lists to JSON strings. Prevents formula evaluation
    by setting cell.data_type = 's' on the destination cell.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value: Any) -> Any:
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel.

    Excel cells cannot carry timezone offsets, so timestamps are converted
    to UTC and stripped of tzinfo. Invalid dates are kept as raw text.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return cell_text(value)
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def cell_boolean(value: Any) -> str:
    """Normalize completion state to 'completed' or 'open'."""
    if isinstance(value, bool):
        return "completed" if value else "open"
    if isinstance(value, (int, float)):
        return "completed" if value != 0 else "open"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "t", "y", "completed"):
            return "completed"
    return "open"


def validate_path(path_str: str) -> Path:
    """Ensure path does not escape parent directory via traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path {path_str!r} contains '..'; refusing relative traversal.")
    return p


def convert_action_items_to_xlsx(
    source_items: List[Dict[str, Any]],
    destination: str,
    overwrite: bool = False,
) -> int:
    """Build and save an Excel workbook from an array of ActionItem objects."""
    output_path = validate_path(destination)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite)")

    if output_path.parent and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "action_items"

    # Header labels: clarify UTC for timestamp columns
    headers = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill

    count = 0
    for item in source_items:
        if not isinstance(item, dict):
            raise ValueError("Each action item in the export must be a JSON object")

        raw_desc = item.get("description")
        desc = "" if raw_desc is None else str(raw_desc).strip()

        row = (
            cell_text(item.get("id")),
            cell_text(desc),
            cell_boolean(item.get("completed")),
            cell_datetime(item.get("due_at")),
            cell_datetime(item.get("created_at")),
            cell_datetime(item.get("updated_at")),
            cell_text(item.get("conversation_id")),
        )
        sheet.append(row)
        count += 1

        # Format row cells
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    if sheet.max_row > 1:
        sheet.auto_filter.ref = sheet.dimensions

    # Auto-adjust column widths
    for index, name in enumerate(headers, start=1):
        col_letter = get_column_letter(index)
        longest = max(
            len(str(c.value)) if c.value is not None else 0
            for c in sheet[col_letter]
        )
        sheet.column_dimensions[col_letter].width = min(max(len(name), longest) + 3, 60)

    # Atomic write via temporary partial file
    partial = output_path.with_name(f"{output_path.name}.partial.{os.getpid()}")
    try:
        workbook.save(partial)
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite)")
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass
        raise

    return count


def load_input_json(source: Optional[str]) -> List[Dict[str, Any]]:
    """Load JSON from standard input or file path."""
    if source is None or source == "-":
        raw = sys.stdin.read().lstrip("\ufeff")
    else:
        path = validate_path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw = path.read_text(encoding="utf-8-sig")

    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("action_items", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError("Expected an array of action items from omi-cli export.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON export to an Excel (.xlsx) workbook.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to JSON file (or '-' / omit for stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="action_items.xlsx",
        help="Destination Excel file (default: action_items.xlsx)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args()

    try:
        items = load_input_json(args.input)
        count = convert_action_items_to_xlsx(
            source_items=items,
            destination=args.output,
            overwrite=args.overwrite,
        )
        print(f"Exported {count} action item(s) to {args.output}")
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
