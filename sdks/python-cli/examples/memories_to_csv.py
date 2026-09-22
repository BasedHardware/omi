import csv
import json
import os
import sys
from pathlib import Path

FIELDS = ["id", "content", "category", "visibility", "tags", "created_at"]
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def neutralize_formula(val):
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        val = ",".join(str(v) for v in val)
    s = str(val)
    if s.startswith(FORMULA_PREFIXES):
        return "'" + s
    return s

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json memory list'")

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
                    neutralize_formula(item.get("content") or item.get("text")),
                    neutralize_formula(item.get("category") or "general"),
                    neutralize_formula(item.get("visibility") or "private"),
                    neutralize_formula(item.get("tags") or []),
                    neutralize_formula(item.get("created_at")),
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
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
