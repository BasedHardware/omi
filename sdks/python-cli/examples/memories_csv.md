# Convert a memories export to CSV

Use this recipe to analyze and organize your Omi memories in Excel, Google Sheets, Airtable, or Notion. It reads a saved JSON export or streams directly from `omi-cli`, makes no network requests, sanitizes fields against spreadsheet formula injection, and outputs UTF-8 BOM encoding for direct opening in Microsoft Excel.

## 1. Export memories from Omi CLI

Export your memories in JSON format:

```bash
omi --json memory list --limit 200 > memories.json
```

The default limit is 25 items. Use `--limit` to export more — raise the value
as needed, or page through results with `--offset` for large accounts.

Or pipe directly into the converter script without saving an intermediate file.

## 2. Convert to CSV

Run the exporter script:

```bash
# Convert a saved file
python sdks/python-cli/examples/memories_to_csv.py memories.json -o memories.csv

# Or pipe directly from Omi CLI
omi --json memory list | python sdks/python-cli/examples/memories_to_csv.py - -o memories.csv
```

## 3. Filtering and Sorting

Filter memories by category, visibility, or specific tag:

```bash
# Filter by category (e.g. work and learnings)
python sdks/python-cli/examples/memories_to_csv.py memories.json --category work,learnings -o work_memories.csv

# Filter by visibility (e.g. only private facts)
python sdks/python-cli/examples/memories_to_csv.py memories.json --visibility private -o private_memories.csv

# Filter by tag
python sdks/python-cli/examples/memories_to_csv.py memories.json --tag python -o python_memories.csv

# Sort by category or chronologically ascending
python sdks/python-cli/examples/memories_to_csv.py memories.json --sort category -o categorized.csv
```

## Output Schema

The CSV contains the following standard columns:

| Column | Description |
|---|---|
| `id` | Unique identifier for the memory |
| `category` | Classification category (e.g. `work`, `skills`, `learnings`) |
| `content` | Sanitized text description of the recorded memory |
| `tags` | Comma-separated tags attached to the memory |
| `visibility` | Visibility level (`public` or `private`) |
| `created_at` | Normalized timestamp in `YYYY-MM-DD HH:MM:SS` UTC |

## Spreadsheet Security

Spreadsheet software like Microsoft Excel or Google Sheets interprets cells starting with `=`, `+`, `-`, or `@` as formulas. To prevent CSV Formula Injection attacks, `memories_to_csv.py` automatically prepends a single quote (`'`) to any cell value that starts with these characters.
