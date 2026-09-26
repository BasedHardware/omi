#!/usr/bin/env python3
"""Convert an omi action-items JSON export to a UTF-8-BOM CSV file.

Usage
-----
    omi --json action-item list > action_items.json
    python scripts/action_items_to_csv.py action_items.json [output.csv]

The output defaults to ``action_items.csv`` in the current directory.
UTF-8 BOM (utf-8-sig) is used so Excel opens the file without a manual
import wizard.
"""

import csv
import json
import sys
from pathlib import Path

# Columns written to the CSV, in order.
FIELDS = ["id", "description", "completed", "due_at", "created_at"]

# Characters that spreadsheet applications treat as formula starters.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: str) -> str:
    """Prefix spreadsheet formula starters with a single quote.

    This follows the OWASP CSV Injection guidance and the pattern used in
    other examples in this repository.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def convert(src: Path, dst: Path) -> int:
    """Read *src* JSON, write *dst* CSV.  Returns the number of rows written."""
    with src.open(encoding="utf-8") as fh:
        data = json.load(fh)

    # The JSON export is either a bare list or {"items": [...]}
    if isinstance(data, dict):
        items = data.get("items", [])
    else:
        items = data

    with dst.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=FIELDS,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for item in items:
            row = {
                "id": _safe(str(item.get("id", ""))),
                "description": _safe(str(item.get("description", ""))),
                "completed": item.get("completed", False),
                "due_at": _safe(str(item.get("due_at") or "")),
                "created_at": _safe(str(item.get("created_at", ""))),
            }
            writer.writerow(row)

    return len(items)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit("Usage: action_items_to_csv.py <action_items.json> [output.csv]")

    src = Path(args[0])
    dst = Path(args[1]) if len(args) > 1 else Path("action_items.csv")

    if not src.exists():
        sys.exit(f"Input file not found: {src}")

    count = convert(src, dst)
    print(f"Wrote {count} action item(s) to {dst}")


if __name__ == "__main__":
    main()
