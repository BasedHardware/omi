# Convert a memory-list export to CSV

Use this recipe to review memory metadata in a spreadsheet (Excel, Google Sheets). It reads a saved JSON export, makes no network requests, and neutralizes formula injection. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file.

Convert to CSV:

```sh
python memories_to_csv.py memories.json memories.csv
```

The script includes formula-injection protection (prefixes potential formula cells with `'`), writes UTF-8 with BOM (`utf-8-sig`) for seamless opening in Microsoft Excel, and uses atomic file replacement.
