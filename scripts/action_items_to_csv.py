"""Convert an Omi action-items JSON export to a CSV file.

Usage
-----
1. Export action items to JSON::

       omi --json action-item list > action_items.json

2. Run this script::

       python action_items_to_csv.py

Output: action_items.csv (UTF-8 with BOM for Excel compatibility)

Note
----
Python's ``csv`` module handles CSV structure quoting only.  The
``sanitize`` function below is what prevents spreadsheet applications
from executing formula-injection payloads (values starting with
``=``, ``+``, ``-``, or ``@``).
See: https://owasp.org/www-community/attacks/CSV_Injection
"""

import csv
import json

INPUT_FILE = "action_items.json"
OUTPUT_FILE = "action_items.csv"

FIELDS = ["id", "description", "completed", "due_at", "created_at"]


def sanitize(value):
    """Prevent formula injection in spreadsheet applications.

    Fields that start with =, +, -, or @ are prefixed with a single quote
    so spreadsheet applications treat them as plain text.
    See: https://owasp.org/www-community/attacks/CSV_Injection
    """
    s = str(value)
    if s.startswith(("=", "+", "-", "@")):
        return "'" + s
    return s


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        items = json.load(f)

    # utf-8-sig writes the BOM Excel needs to detect UTF-8 automatically
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for item in items:
            writer.writerow([
                sanitize(item.get("id", "")),
                sanitize(item.get("description", "")),
                item.get("completed", False),
                item.get("due_at") or "",
                item.get("created_at") or "",
            ])

    print(f"Wrote {len(items)} action item(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
