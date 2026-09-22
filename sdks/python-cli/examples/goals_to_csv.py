import csv
import json
import os
import sys
from pathlib import Path

FIELDS = ("id", "title", "description", "target_date", "progress", "created_at")


def spreadsheet_text(value):
    """Neutralize spreadsheet formula injection risks."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def format_progress(item):
    """Format goal progress from GoalResponse fields (current_value, target_value, metric)."""
    curr = item.get("current_value")
    tgt = item.get("target_value")
    metric = (item.get("metric") or "").strip()
    if curr is not None and tgt is not None:
        return f"{curr}/{tgt} {metric}".strip()
    if curr is not None:
        return f"{curr} {metric}".strip()
    return str(item.get("progress") or "")


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("goals", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(FIELDS)
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = [
                    item.get("id", ""),
                    spreadsheet_text(item.get("title") or item.get("name")),
                    spreadsheet_text(item.get("description") or ""),
                    item.get("horizon_at") or item.get("target_date") or item.get("target_at") or "",
                    spreadsheet_text(format_progress(item)),
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
        print("Usage: python goals_to_csv.py <source.json> <destination.csv>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
