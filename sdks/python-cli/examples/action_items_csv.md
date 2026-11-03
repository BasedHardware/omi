# Convert action-item exports to CSV and TSV spreadsheets

Use this recipe to convert Omi action items and task exports into CSV or TSV
files for easy importing into Todoist, Notion Databases, Google Sheets, Microsoft
Excel, or Unix terminal pipelines. It supports direct pipeline streaming from
`omi-cli`, completion status filtering, custom date sorting, and built-in spreadsheet
formula injection defense.

Requires Python 3.10+ and an authenticated `omi-cli`.

## Quick Start

### 1. Pipe directly from omi CLI to CSV

Export all tasks into a CSV file in one command:

```sh
omi --json action-item list --limit 200 | python action_items_to_csv.py - -o tasks.csv
```

### 2. Export only pending / open tasks for Todoist or Notion

Filter out already completed tasks so you only import actionable items:

```sh
omi --json action-item list --limit 200 | python action_items_to_csv.py - --status open -o open_tasks.csv
```

### 3. Open directly in Microsoft Excel

If opening in desktop Excel on Windows or macOS, pass `--excel-bom` to prepend the
UTF-8 byte-order mark (BOM) so international characters and emojis display cleanly:

```sh
omi --json action-item list | python action_items_to_csv.py - --excel-bom -o tasks_excel.csv
```

### 4. Unix Pipeline (TSV mode)

Export as tab-separated values (TSV) to process with tools like `cut`, `awk`, or `grep`:

```sh
# Print description and due date using awk
omi --json action-item list | python action_items_to_csv.py - --tsv | awk -F'\t' '{print $2, "--> Due:", $4}'
```

## Security: Spreadsheet Formula Injection Defense

When exporting untrusted text (such as transcripts transcribed from audio) into CSV,
malicious or accidental leading characters like `=`, `+`, `-`, or `@` could trigger
formula execution or DDE commands in Excel or LibreOffice.

`action_items_to_csv.py` automatically detects leading formula characters in text fields
and prefixes them with a single quote (`'`), neutralizing formula execution while preserving
the visible text inside spreadsheet viewers. If you specifically need literal formulas,
pass `--no-formula-defense`.

## Command-Line Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `source` | Path to JSON file, or `-` for stdin | `-` |
| `-o`, `--output` | Destination CSV file path | stdout |
| `--status` | Filter by `all`, `open`, or `completed` | `all` |
| `--sort-by` | Sort by `due_at`, `created_at`, `updated_at`, `status`, `id` | `none` |
| `--reverse` | Reverse sort order | False |
| `--tsv` | Output Tab-Separated Values (TSV) | False |
| `--bool-format` | Format of `completed`: `true_false`, `boolean`, `check`, `int` | `true_false` |
| `--excel-bom` | Prepend UTF-8 BOM for Microsoft Excel | False |
| `--no-header` | Omit CSV header row (useful for append scripts) | False |
| `--no-formula-defense` | Disable automatic formula escaping | False |
