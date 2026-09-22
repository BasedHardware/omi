import csv
import json
import os
import sys
from pathlib import Path

FIELDS = ["screenshot_id", "timestamp", "app_name", "window_title", "similarity", "ocr_preview"]
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def spreadsheet_text(value):
    if value is None:
        return ""
    s = str(value)
    if s.startswith(FORMULA_PREFIXES):
        return "'" + s
    return s

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("results", data.get("history", data.get("items", [])))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array or 'results' list from 'omi --json local search-screen'")

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
                    spreadsheet_text(item.get("screenshot_id") or item.get("id")),
                    spreadsheet_text(item.get("timestamp") or item.get("created_at")),
                    spreadsheet_text(item.get("app_name") or item.get("app")),
                    spreadsheet_text(item.get("window_title") or item.get("title")),
                    spreadsheet_text(item.get("similarity")),
                    spreadsheet_text(item.get("ocr_preview") or item.get("text") or item.get("ocr_text")),
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
        print("Usage: python screen_history_to_csv.py <source.json> <destination.csv>", file=sys.stderr)
        sys.exit(1)
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
