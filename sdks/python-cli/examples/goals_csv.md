# Convert goals export to CSV

Use this recipe to export goals and milestones from Omi to a spreadsheet (Google Sheets, Excel, Airtable). It reads a saved JSON export, makes no network requests, and neutralizes formula injection. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 100 goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Convert to CSV:

```sh
python goals_to_csv.py goals.json goals.csv
```

Open `goals.csv` in your spreadsheet application to track progress, milestones, and target completion dates.
