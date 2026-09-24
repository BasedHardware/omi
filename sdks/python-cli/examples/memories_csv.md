# Convert memories export to CSV

Use this recipe to export Omi memories, facts, and learnings to a standard CSV spreadsheet for review in Excel, Google Sheets, Airtable, or LibreOffice.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

Export memories using the CLI and convert immediately:

```sh
# Export directly via pipeline
omi --json memory list | python memories_to_csv.py - -o memories.csv

# Or export from a saved JSON file
python memories_to_csv.py memories.json -o memories.csv
```

## Running the Recipe

You can run the bundled [`memories_to_csv.py`](memories_to_csv.py) script:

```sh
python sdks/python-cli/examples/memories_to_csv.py memories.json -o memories.csv
```

### Multiple Pages & Merging

If you have paginated JSON files from multiple export batches:

```sh
python memories_to_csv.py page1.json page2.json -o all_memories.csv
```

## Output Columns

| Column | Description |
|---|---|
| `id` | Unique identifier of the memory item |
| `content` | The memory text or captured knowledge statement |
| `category` | Classification tag (e.g. `work`, `skills`, `preferences`) |
| `manually_added` | `true` if manually created; `false` if auto-extracted |
| `created_at` | UTC timestamp in `YYYY-MM-DD HH:MM:SS` format |
| `updated_at` | UTC timestamp in `YYYY-MM-DD HH:MM:SS` format |

## Security & Encoding Notes

- **CSV Formula Injection Safeguard**: Values beginning with `=`, `+`, `-`, or `@` are safely apostrophe-escaped to prevent code/formula execution in Excel or Calc.
- **UTF-8 with BOM (`utf-8-sig`)**: Ensures international characters and symbols render correctly without mojibake when opened directly in Microsoft Excel.
