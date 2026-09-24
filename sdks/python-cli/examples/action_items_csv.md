# Put your action items into a spreadsheet (.csv)

Use this recipe to export your personal action items, tasks, and follow-ups captured by Omi into a clean, spreadsheet-ready CSV file for Microsoft Excel, Google Sheets, Apple Numbers, or Python/Pandas data pipelines.

It reads saved JSON exports or piped input via `stdin`, makes zero network requests, and generates a standards-compliant CSV file encoded with a UTF-8 Byte Order Mark (BOM) so characters render perfectly across all platforms without manual import configuration.

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli`

## 1. Export your action items

Export your action items (up to 200 per page):

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

If you have more than 200 items, retrieve subsequent pages into separate files:

```sh
omi --json action-item list --limit 200 --offset 200 > action_items_200.json
```

## 2. Generate the CSV file

Run the companion converter script [`action_items_to_csv.py`](action_items_to_csv.py):

```sh
# Basic export
python sdks/python-cli/examples/action_items_to_csv.py action_items_0.json tasks.csv

# Direct pipeline streaming via stdin
omi --json action-item list --limit 200 | python sdks/python-cli/examples/action_items_to_csv.py - tasks.csv

# Filter only open / pending tasks
python sdks/python-cli/examples/action_items_to_csv.py action_items_0.json pending_tasks.csv --status open

# Combine multiple pages with automatic deduplication by task ID
python sdks/python-cli/examples/action_items_to_csv.py action_items_0.json action_items_200.json all_tasks.csv --force
```

### CLI Options

| Argument | Description | Default |
|:---|:---|:---|
| `SOURCE ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `DESTINATION` | Destination path for the `.csv` file | *(required)* |
| `--status` | Filter items by status: `all`, `open` (or `pending`), `completed` (or `done`) | `all` |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

## 3. CSV Columns and Sample Output

The exported CSV provides the following 8 structured fields:

1. `id` - Unique action item identifier.
2. `description` - Task description or action text.
3. `completed` - Boolean completion flag (`TRUE` or `FALSE`).
4. `status` - Normalized status (`open` or `completed`).
5. `due_at` - Due date timestamp (ISO 8601, or empty).
6. `created_at` - Task creation timestamp (ISO 8601).
7. `updated_at` - Last update timestamp (ISO 8601, or empty).
8. `conversation_id` - Identifier of the origin conversation where the action was captured.

### Sample CSV Row

```csv
id,description,completed,status,due_at,created_at,updated_at,conversation_id
0192e4b2-a912,Send quarterly report to leadership,FALSE,open,2026-09-30T17:00:00Z,2026-09-24T10:00:00Z,2026-09-24T10:05:00Z,0192e401-cc87
```

## 4. Security & Spreadsheet Compatibility

- **Formula Injection (DDE) Protection**: Any string field starting with dangerous spreadsheet formula triggers (`=`, `+`, `-`, `@`) is safely escaped with a leading single quote (`'`), preventing malicious formula execution when opened in Excel or Calc.
- **UTF-8 BOM Header**: Includes `\xef\xbb\xbf` so Microsoft Excel automatically recognizes Unicode characters without requiring manual import wizards.
- **Automated Verification**: Run the automated test suite with:
  ```sh
  python sdks/python-cli/tests/test_action_items_to_csv.py
  ```
