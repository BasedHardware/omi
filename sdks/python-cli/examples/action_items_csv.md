# Convert an action-items export to CSV

Use this recipe to review, filter, or import Omi tasks and follow-ups in a spreadsheet (Excel, Google Sheets, Notion, Todoist, Airtable). It reads a saved JSON export, makes no network requests, and sanitizes fields against CSV formula injection.

You need Python 3.10+ and an authenticated `omi-cli`.

## 1. Export action items from Omi

Export your action items (default limit is 100; use `--limit` and `--offset` to page through all of them):

```sh
omi --json action-item list --limit 100 > action_items.json
```

To export more than 100 items, page through them and combine the results:

```sh
omi --json action-item list --limit 100 --offset 0   > page1.json
omi --json action-item list --limit 100 --offset 100 > page2.json
# … repeat until an empty page is returned
```

> **Note:** One export page is not guaranteed to be a complete account backup if you have more than 100 action items.

Or filter for open items only directly from the CLI:

```sh
omi --json action-item list --open > open_action_items.json
```

## 2. Convert to CSV

Run `action_items_to_csv.py`:

```sh
python action_items_to_csv.py action_items.json --output action_items.csv
```

Or pipe directly from `omi-cli` without intermediate files:

```sh
omi --json action-item list | python action_items_to_csv.py - --output action_items.csv
```

Filter open or completed items during export:

```sh
# Export only open (pending) tasks
omi --json action-item list | python action_items_to_csv.py - --status open -o open_tasks.csv

# Export only completed tasks
omi --json action-item list | python action_items_to_csv.py - --status completed -o completed_tasks.csv
```

## 3. Spreadsheet Safety & Features

* **UTF-8 with BOM (`utf-8-sig`)**: Ensures international characters, accents, and emojis render correctly when double-clicked in Microsoft Excel.
* **Formula injection mitigation**: Cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r` are quoted with a leading apostrophe (`'`) to prevent spreadsheet DDE code execution.
* **Normalized timestamps**: Converts ISO timestamps to consistent UTC `YYYY-MM-DD HH:MM:SS` strings compatible with spreadsheet sorting.
* **Stdlib only**: Uses only Python's built-in `csv`, `json`, `sys`, and `datetime` libraries with zero external dependencies.
