"""Convert an omi-cli goal export to a CSV spreadsheet.

Reads JSON produced by `omi --json goal list --limit 100 --include-inactive`
(or piped via stdin), and generates a CSV file with progress metrics,
formula injection protection, and envelope unwrapping.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

FIELDS = (
    "id",
    "title",
    "goal_type",
    "target_value",
    "current_value",
    "min_value",
    "max_value",
    "unit",
    "is_active",
    "progress_pct",
    "created_at",
    "updated_at",
)


def validate_path(path_str: str) -> Path:
    """Validate that path does not attempt path traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: {path_str}")
    return p


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Values starting with '=', '+', '-', or '@' are prefixed with an apostrophe
    to prevent CSV formula execution in spreadsheet software.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)

    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def clean_num(val: Any) -> str:
    """Format numeric values without trailing .0 if integer."""
    if val is None:
        return "0"
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else f"{f:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return str(val)


def calculate_progress_pct(item: dict[str, Any]) -> float:
    """Calculate normalized completion percentage (0.0 to 100.0)."""
    goal_type = str(item.get("goal_type") or "").strip().lower()

    try:
        cur = float(item.get("current_value") or 0.0)
    except (ValueError, TypeError):
        cur = 0.0

    try:
        target = float(item.get("target_value") or 0.0)
    except (ValueError, TypeError):
        target = 0.0

    if goal_type == "boolean":
        return 100.0 if cur >= target and target > 0 else (100.0 if cur >= 1.0 else 0.0)

    if goal_type == "scale":
        try:
            min_val = float(item.get("min_value") or 0.0)
            max_val = float(item.get("max_value") or 0.0)
        except (ValueError, TypeError):
            min_val, max_val = 0.0, 0.0

        if max_val > min_val:
            pct = ((cur - min_val) / (max_val - min_val)) * 100.0
            return max(0.0, min(100.0, pct))
        return 0.0

    # Default numeric goal
    if target > 0.0:
        return max(0.0, (cur / target) * 100.0)

    return 0.0


def convert(
    source: str | Path,
    destination: str | Path,
    overwrite: bool = False,
) -> int:
    """Convert goals export JSON to a CSV file.

    Returns the count of exported goals.
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
        for key in ("goals", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            raise ValueError("Expected a JSON array or envelope object containing 'goals'")
    else:
        raise ValueError("Expected a JSON array or dictionary object")

    rows: list[list[str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal item must be a JSON object")

        pct = calculate_progress_pct(item)
        is_active = item.get("is_active")
        is_active_str = "true" if is_active is True else ("false" if is_active is False else "")

        row = [
            spreadsheet_text(item.get("id")),
            spreadsheet_text(item.get("title")),
            spreadsheet_text(item.get("goal_type")),
            clean_num(item.get("target_value")),
            clean_num(item.get("current_value")),
            clean_num(item.get("min_value")),
            clean_num(item.get("max_value")),
            spreadsheet_text(item.get("unit")),
            is_active_str,
            f"{pct:.1f}%",
            spreadsheet_text(item.get("created_at")),
            spreadsheet_text(item.get("updated_at")),
        ]
        rows.append(row)

    output_path = validate_path(str(destination))
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file '{output_path}' already exists. Use --overwrite to replace it."
        )

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(rows)
    csv_bytes = buf.getvalue().encode("utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.partial")
    try:
        partial.write_bytes(csv_bytes)
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise

    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an omi-cli goal export to a CSV spreadsheet."
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
        help="Output CSV file path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args()

    try:
        count = convert(args.input, args.output, overwrite=args.overwrite)
        print(f"Exported {count} goal(s) to {args.output}")
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")


if __name__ == "__main__":
    main()
