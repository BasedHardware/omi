import csv
import json
import os
import sys
from pathlib import Path

FIELDS = ("id", "content", "category", "visibility", "tags", "created_at")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, lineterminator="\r\n")
            writer.writerow(FIELDS)
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = [
                    item.get("id", ""),
                    spreadsheet_text(item.get("content") or item.get("text") or ""),
                    spreadsheet_text(item.get("category") or ""),
                    spreadsheet_text(item.get("visibility") or ""),
                    spreadsheet_text(item.get("tags") or []),
                    item.get("created_at") or "",
                ]
                writer.writerow(row)

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python memories_to_csv.py <source.json> <destination.csv>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
