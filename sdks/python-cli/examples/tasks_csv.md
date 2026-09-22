# Convert tasks export to CSV

Use this recipe to export action tasks to CSV for import into Todoist, Notion, or spreadsheets. It reads a saved JSON export, makes no network requests, and neutralizes formula injection. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export action tasks:

```sh
omi --json task list --limit 200 > tasks.json
```

Convert to CSV:

```sh
python tasks_to_csv.py tasks.json tasks.csv
```

The resulting `tasks.csv` is sanitized against spreadsheet injection attacks and uses UTF-8 with BOM for Excel compatibility.
