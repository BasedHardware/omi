#!/usr/bin/env python3
"""Convert an Omi goals JSON export to an Excel workbook (.xlsx).

Creates a structured spreadsheet with native numeric values, progress percentages,
naive UTC datetime cells, frozen headers, autofilters, auto-fit columns, and explicit
string typing to neutralize spreadsheet formula injection.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list --limit 100 --include-inactive | python goals_to_xlsx.py - -o goals.xlsx

    # Convert an existing export file
    python goals_to_xlsx.py goals.json -o goals.xlsx --overwrite
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

FIELDS = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "unit",
    "progress_pct",
    "is_active",
    "created_at",
    "updated_at",
)

DATETIME_FORMAT = "yyyy-mm-dd hh:mm:ss"
PERCENT_FORMAT = "0.0%"


def cell_text(value: Any) -> Optional[str]:
    """Render exported field as text.

    Coerces dicts/lists to JSON strings. Prevents formula evaluation
    by setting cell.data_type = 's' on the destination cell.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_number(value: Any) -> Optional[Union[int, float]]:
    """Parse numeric values for native Excel number storage."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        v = value.strip()
        try:
            if "." in v:
                return float(v)
            return int(v)
        except ValueError:
            return None
    return None


def cell_datetime(value: Any) -> Any:
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel.

    Excel cells cannot carry timezone offsets, so timestamps are normalized
    to UTC and stripped of tzinfo. Invalid strings remain as raw text.
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
    """Normalize goal status to 'active' or 'inactive'."""
    if isinstance(value, bool):
        return "active" if value else "inactive"
    if isinstance(value, (int, float)):
        return "active" if value != 0 else "inactive"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "active", "t"):
            return "active"
    return "inactive"


def calculate_progress_pct(item: Dict[str, Any]) -> Optional[float]:
    """Derive progress percentage from current and target metrics."""
    goal_type = str(item.get("goal_type") or "").lower()
    current = item.get("current_value")
    target = item.get("target_value")

    if goal_type == "boolean":
        if current is not None:
            return 100.0 if bool(current) else 0.0
        return 0.0 if item.get("is_active", True) else 100.0

    if current is not None and target is not None:
        try:
            curr_f = float(current)
            target_f = float(target)
            if target_f != 0:
                min_v = item.get("min_value")
                if min_v is not None and goal_type == "scale":
                    min_f = float(min_v)
                    span = target_f - min_f
                    if span != 0:
                        pct = ((curr_f - min_f) / span) * 100.0
                        return round(pct, 1)
                pct = (curr_f / target_f) * 100.0
                return round(pct, 1)
        except (ValueError, TypeError):
            pass
    return None


def validate_path(path_str: str) -> Path:
    """Ensure path does not escape parent directory via traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path {path_str!r} contains '..'; refusing relative directory traversal.")
    return p


def convert_goals_to_xlsx(
    source_items: List[Dict[str, Any]],
    destination: str,
    overwrite: bool = False,
) -> int:
    """Build and save an Excel workbook from an array of Goal objects."""
    output_path = validate_path(destination)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite)")

    if output_path.parent and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "goals"

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
            raise ValueError("Each goal in the export must be a JSON object")

        raw_title = item.get("title")
        title = "" if raw_title is None else str(raw_title).strip()

        row = (
            cell_text(item.get("id")),
            cell_text(title),
            cell_text(item.get("goal_type")),
            cell_number(item.get("current_value")),
            cell_number(item.get("target_value")),
            cell_text(item.get("unit")),
            cell_number(calculate_progress_pct(item)),
            cell_boolean(item.get("is_active")),
            cell_datetime(item.get("created_at")),
            cell_datetime(item.get("updated_at")),
        )
        sheet.append(row)
        count += 1

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

    # Atomic write via temporary partial file with safe no-clobber protection
    partial = output_path.with_name(f"{output_path.name}.partial.{os.getpid()}")
    try:
        workbook.save(partial)
        if overwrite:
            os.replace(partial, output_path)
        else:
            try:
                os.link(partial, output_path)
                partial.unlink()
            except FileExistsError:
                raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite)")
            except OSError:
                if output_path.exists():
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
    """Load JSON from standard input or file path, handling UTF-8 BOM."""
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
        for key in ("goals", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError("Expected an array of goals from omi-cli export.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON export to an Excel (.xlsx) workbook.",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_opt",
        default=None,
        help="Path to JSON file (or '-' for stdin)",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to JSON file (or '-' / omit for stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="goals.xlsx",
        help="Destination Excel file (default: goals.xlsx)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args(argv)

    try:
        source = args.input_opt or args.input or "-"
        items = load_input_json(source)
        count = convert_goals_to_xlsx(
            source_items=items,
            destination=args.output,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            sys.stderr.write(f"Exported {count} goal(s) to {args.output}\n")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
