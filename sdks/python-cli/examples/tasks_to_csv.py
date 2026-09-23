import csv
import json
import os
import sys
from pathlib import Path

FIELDS = ["id", "description", "completed", "created_at", "updated_at", "due_at", "completed_at", "conversation_id"]
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def neutralize_formula(val):
    if val is None:
        return ""
    s = str(val)
    if s.startswith(FORMULA_PREFIXES):
        return "'" + s
    return s

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("action_items", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json action-item list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(FIELDS)
            for item in items:
                if not isinstance(item, dict):
                    continue
                row = [
                    neutralize_formula(item.get("id")),
                    neutralize_formula(item.get("description") or item.get("content")),
                    str(bool(item.get("completed"))).lower(),
                    neutralize_formula(item.get("created_at")),
                    neutralize_formula(item.get("updated_at")),
                    neutralize_formula(item.get("due_at") or item.get("due_date")),
                    neutralize_formula(item.get("completed_at")),
                    neutralize_formula(item.get("conversation_id")),
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
        print("Usage: python tasks_to_csv.py <source.json> <destination.csv>", file=sys.stderr)
        sys.exit(1)
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
