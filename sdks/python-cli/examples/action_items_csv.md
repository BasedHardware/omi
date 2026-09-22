# Convert an action-item list export to CSV

Use this recipe to import action items into spreadsheets, Notion databases, Asana, or task tracking tables. It reads a saved JSON export, makes no network requests, and neutralizes formula injection. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Convert to CSV:

```sh
python action_items_to_csv.py action_items.json action_items.csv
```

The script features formula-injection prevention and atomic writes with `.partial` safety buffers.


## Pagination Note
`omi --json action-item list --limit 200 --offset 0` retrieves one page of up to 200 items. To export a complete history across multiple pages, increment `--offset 200` until an empty array is returned.
