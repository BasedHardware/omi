"""Export memories JSON payload to spreadsheet-safe CSV with BOM and formula guard (#20285)."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

FIELDS = ("id", "category", "visibility", "content", "tags", "created_at", "updated_at")


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Prefixes text starting with =, +, -, @, \t, \r, \n with an apostrophe
    to prevent formula injection upon spreadsheet import.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def memories_to_csv(items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    for item in items:
        tags = item.get("tags")
        tag_str = ", ".join(str(t) for t in tags) if isinstance(tags, list) else tags
        values = (
            item.get("id"),
            item.get("category"),
            item.get("visibility"),
            item.get("content"),
            tag_str,
            item.get("created_at"),
            item.get("updated_at"),
        )
        writer.writerow([spreadsheet_text(v) for v in values])
    return buffer.getvalue()


def convert(source: str, destination: str) -> None:
    data = json.loads(Path(source).read_bytes())
    if isinstance(data, dict):
        items = data.get("memories") or data.get("items") or data.get("data") or []
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Expected JSON array or envelope object containing memories")

    csv_text = memories_to_csv(items)
    output_path = Path(destination)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(csv_text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
