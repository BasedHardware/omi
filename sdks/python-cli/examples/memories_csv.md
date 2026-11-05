# Export Memories to CSV

This recipe demonstrates converting memory exports from the Omi CLI into a spreadsheet-safe CSV file.

## Usage

Export your memories in JSON format using `omi`:

```sh
omi --json memory list --limit 200 > memories.json
# Or use the built-in export command:
omi memory export --format json > memories.json
```

Then run the converter script:

```sh
python memories_to_csv.py memories.json memories.csv
```

## Features

- Prepends UTF-8 BOM (`\ufeff`) for proper encoding auto-detection in Microsoft Excel and Google Sheets.
- Formula Injection Protection: Prefixes cell values starting with `=`, `+`, `-`, `@`, `\t`, `\r`, or `\n` with an apostrophe (`'`).
- Handles array or wrapped envelope JSON structures (`memories`, `items`, `data`).
