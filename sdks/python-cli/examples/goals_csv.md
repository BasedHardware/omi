# Convert a goal-list export to CSV

Use this recipe to review, sort, and analyze your Omi tracked goals in a
spreadsheet (Excel, Google Sheets, LibreOffice, or Airtable). It reads a saved
JSON export, makes no network requests, calculates completion percentages, and
sanitizes values against spreadsheet formula injection.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export tracked goals:

```sh
omi --json goal list --limit 100 > goals.json
```

To include inactive/completed goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Run the converter:

```sh
python goals_to_csv.py goals.json --output goals.csv
```

Or stream directly from the CLI without saving a temporary JSON file:

```sh
omi --json goal list | python goals_to_csv.py - --status active -o active_goals.csv
```

Import the result as comma-delimited text in your spreadsheet. Accented characters
render accurately thanks to the UTF-8 BOM, timestamps are normalized to UTC, and
percentage progress is pre-computed.
