#!/usr/bin/env python3
"""Convert an Omi action-items JSON export to CSV.

Reads an array of ActionItem objects from a file or stdin, normalises
timestamps and booleans, protects against spreadsheet formula injection,
and writes an RFC 4180 compliant CSV file.
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = (
    "id",
    "description",
    "completed",
    "due_at",
    "created_at",
    "updated_at",
    "conversation_id",
)

INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value: Any) -> str:
    """Sanitize a value for safe inclusion in spreadsheets.

    Guards against formula injection (CSV injection) when opened in Excel
    or Google Sheets. Checks both direct injection prefixes and leading
    space-padded formulas to prevent execution.
    """
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in INJECTION_PREFIXES:
        return "'" + text
    stripped = text.lstrip(" ")
    if stripped and stripped[0] in INJECTION_PREFIXES:
        return "'" + text
    return text


def parse_timestamp(value: Any) -> Optional[str]:
    """Normalise an ISO 8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS'."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def parse_boolean(value: Any) -> str:
    """Normalise completion flags to 'true' or 'false'."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value != 0 else "false"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "t", "y"):
            return "true"
        if v in ("false", "0", "no", "f", "n"):
            return "false"
    return "false"


def transform_item(item: Dict[str, Any]) -> Dict[str, str]:
    """Transform a single raw ActionItem dictionary into a sanitized CSV row."""
    raw_desc = item.get("description")
    desc_str = "" if raw_desc is None else str(raw_desc).strip()

    return {
        "id": spreadsheet_safe(item.get("id")),
        "description": spreadsheet_safe(desc_str),
        "completed": parse_boolean(item.get("completed")),
        "due_at": spreadsheet_safe(parse_timestamp(item.get("due_at"))),
        "created_at": spreadsheet_safe(parse_timestamp(item.get("created_at"))),
        "updated_at": spreadsheet_safe(parse_timestamp(item.get("updated_at"))),
        "conversation_id": spreadsheet_safe(item.get("conversation_id")),
    }


def validate_output_path(output_path: str) -> Path:
    """Validate that the destination path does not escape into parent directories."""
    path = Path(output_path)
    if ".." in path.parts:
        raise ValueError(f"Output path {output_path!r} contains '..'; refusing relative traversal.")
    return path


def convert_action_items_to_csv(
    items: List[Dict[str, Any]],
    output_path: str,
    include_bom: bool = False,
) -> int:
    """Write sanitized action items into an RFC 4180 CSV file atomically."""
    dest = validate_output_path(output_path)
    if dest.parent and not dest.parent.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)

    encoding = "utf-8-sig" if include_bom else "utf-8"

    # Write to a temporary file in the same directory for atomic replace
    temp_dir = dest.parent if dest.parent.is_dir() else Path(".")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        newline="",
        delete=False,
        dir=temp_dir,
    ) as tmp_file:
        tmp_name = tmp_file.name
        try:
            writer = csv.DictWriter(
                tmp_file,
                fieldnames=FIELDS,
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\r\n",
            )
            writer.writeheader()
            count = 0
            for item in items:
                if isinstance(item, dict):
                    writer.writerow(transform_item(item))
                    count += 1
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        except Exception:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise

    # Atomically replace destination file with cleanup on failure
    try:
        os.replace(tmp_name, dest)
    except Exception:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        raise
    return count


def load_input_json(source: Optional[str]) -> List[Dict[str, Any]]:
    """Load and parse JSON action items from a file path or stdin."""
    if source is None or source == "-":
        raw = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw = path.read_text(encoding="utf-8")

    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Support wrapped responses like {"action_items": [...]} or {"items": [...]}
        for key in ("action_items", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError("JSON input must be an array or object of action items.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON export to CSV.",
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
        default="action_items.csv",
        help="Output CSV path (default: action_items.csv)",
    )
    parser.add_argument(
        "--excel",
        action="store_true",
        help="Include UTF-8 BOM for direct compatibility with Microsoft Excel",
    )

    args = parser.parse_args()

    try:
        items = load_input_json(args.input)
        count = convert_action_items_to_csv(
            items=items,
            output_path=args.output,
            include_bom=args.excel,
        )
        print(f"Exported {count} action item(s) to {args.output}")
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
