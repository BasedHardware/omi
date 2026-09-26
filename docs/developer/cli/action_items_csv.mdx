---
title: Export Action Items to CSV
---

Export your Omi action items to a CSV file for use in spreadsheet applications such as Excel or LibreOffice Calc.

## Prerequisites

```bash
pip install omi-cli
```

> **Note:** Install `omi-cli`, not `omi`. The bare `omi` name on PyPI is an unrelated package.

## Step 1 — Export JSON

```bash
omi --json action-item list > action_items.json
```

## Step 2 — Convert to CSV

Save the script below as `action_items_to_csv.py`, then run:

```bash
python action_items_to_csv.py
```

This creates `action_items.csv` in the current directory.

## Script

```python
# action_items_to_csv.py
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
```

## Sample output

```
id,description,completed,due_at,created_at
3f6a1b2c-...,Buy groceries,False,,2024-11-01T09:00:00Z
7c9d4e5f-...,Schedule dentist appointment,True,2024-11-15T00:00:00Z,2024-11-01T09:05:00Z
```

## Notes

- **Formula injection:** Values starting with `=`, `+`, `-`, or `@` are prefixed with `'` so spreadsheet applications render them as plain text instead of executing them as formulas. Note that Python's `csv` module handles CSV structure quoting only; the `sanitize` function is what prevents spreadsheet formula execution.
- **Excel UTF-8:** The file is written with the UTF-8 BOM (`utf-8-sig`) so Excel opens it correctly without a manual import step.
- **`completed`** is a boolean (`True`/`False`); filter or reformat it in your spreadsheet as needed.
