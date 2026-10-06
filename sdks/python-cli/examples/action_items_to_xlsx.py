"""Convert Omi action items JSON exports into a formatted Excel workbook (.xlsx).

Features:
- Real Excel datetime cells in UTC for due_at, created_at, and updated_at.
- Native boolean values for completion status.
- Explicit string typing to prevent spreadsheet formula injection (=, +, -, @).
- Header row frozen (A2) with bold text and AutoFilter enabled.
- Auto-adjusted column widths.
- Deduplication by task ID across multiple paginated export files.
- Atomic file writes (.partial + os.replace) and directory traversal protection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font
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


def validate_path(target_path: str | Path) -> Path:
    """Validate that path does not escape the current or intended directory."""
    path = Path(target_path)
    if ".." in path.parts:
        raise ValueError(f"Path '{target_path}' contains '..', refusing to traverse directories.")
    return path


def cell_text(value: Any) -> str | None:
    """Coerce value to text safely without executing formulas."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_datetime(value: Any) -> datetime | str | None:
    """Parse an ISO-8601 timestamp into a naive UTC datetime for Excel.

    Excel cannot store explicit timezones in cells. All valid datetimes
    are normalized to UTC and stripped of tzinfo. Unparseable strings
    fall back to plain text to avoid dropping information.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return cell_text(value)
    clean = value.strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return clean
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def cell_boolean(value: Any) -> bool | None:
    """Strictly normalize boolean flags."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "y", "done", "completed"):
            return True
        if lowered in ("false", "0", "no", "n"):
            return False
    return bool(value)


def extract_items(data: Any) -> list[dict[str, Any]]:
    """Extract list of action item objects from raw array or envelope wrappers."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("action_items", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []


def load_input_files(sources: Sequence[str | Path]) -> list[dict[str, Any]]:
    """Load, parse, and deduplicate action items from one or more JSON files."""
    dedup: dict[str, dict[str, Any]] = {}
    anon_items: list[dict[str, Any]] = []

    for src in sources:
        path = validate_path(src)
        raw_bytes = path.read_bytes()
        # Handle optional UTF-8 BOM
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            raw_bytes = raw_bytes[3:]
        parsed = json.loads(raw_bytes.decode("utf-8"))
        items = extract_items(parsed)

        for item in items:
            item_id = item.get("id")
            if item_id:
                dedup[str(item_id)] = item
            else:
                anon_items.append(item)

    return list(dedup.values()) + anon_items


def convert(
    sources: str | Path | Sequence[str | Path],
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> int:
    """Convert JSON exports into an Excel workbook (.xlsx)."""
    if isinstance(sources, (str, Path)):
        sources = [sources]

    dest_path = validate_path(destination)
    if dest_path.exists() and not overwrite:
        raise FileExistsError(f"Destination '{dest_path}' already exists. Use --overwrite to replace.")

    items = load_input_files(sources)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "action_items"

    # Header row
    headers = [f"{name} (UTC)" if name.endswith("_at") else name for name in FIELDS]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    # Populate data rows
    for item in items:
        row = (
            cell_text(item.get("id")),
            cell_text(item.get("description")),
            cell_boolean(item.get("completed")),
            cell_datetime(item.get("due_at")),
            cell_datetime(item.get("created_at")),
            cell_datetime(item.get("updated_at")),
            cell_text(item.get("conversation_id")),
        )
        sheet.append(row)
        current_row = sheet[sheet.max_row]
        for cell in current_row:
            if isinstance(cell.value, datetime):
                cell.number_format = DATETIME_FORMAT
            elif isinstance(cell.value, bool):
                cell.data_type = "b"
            elif isinstance(cell.value, str):
                cell.data_type = "s"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    # Auto-adjust column widths
    for index, name in enumerate(FIELDS, start=1):
        col_letter = get_column_letter(index)
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in sheet[col_letter])
        sheet.column_dimensions[col_letter].width = min(max(len(name), longest) + 2, 70)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = dest_path.with_name(dest_path.name + ".partial")
    try:
        workbook.save(partial_path)
        os.replace(partial_path, dest_path)
    except OSError:
        if partial_path.exists():
            partial_path.unlink()
        raise

    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into an Excel (.xlsx) workbook."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON export files from omi action-item list.")
    parser.add_argument("-o", "--output", required=True, help="Path to write the resulting .xlsx workbook.")
    parser.add_argument(
        "-f", "--overwrite", action="store_true", help="Overwrite the output file if it already exists."
    )

    args = parser.parse_args()
    try:
        count = convert(args.inputs, args.output, overwrite=args.overwrite)
        print(f"Exported {count} action items to {args.output}")
    except (ValueError, FileExistsError, OSError) as exc:
        sys.exit(f"Export failed: {exc}")


if __name__ == "__main__":
    main()
