# Put your goals into a spreadsheet (.csv)

Use this recipe to export your personal goals, OKRs, and milestone targets captured by Omi into a clean, spreadsheet-ready CSV file for Microsoft Excel, Google Sheets, Apple Numbers, or Python/Pandas data pipelines.

It reads saved JSON exports or piped input via `stdin`, makes zero network requests, and generates a standards-compliant CSV file encoded with a UTF-8 Byte Order Mark (BOM) so characters render perfectly across all platforms without manual import configuration.

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli`

## 1. Export your goals

Export your goals (up to 200 per page):

```sh
omi --json goal list --limit 200 --offset 0 > goals_0.json
```

If you have more than 200 goals, retrieve subsequent pages into separate files:

```sh
omi --json goal list --limit 200 --offset 200 > goals_200.json
```

## 2. Generate the CSV file

Run the companion converter script [`goals_to_csv.py`](goals_to_csv.py):

```sh
# Basic export
python sdks/python-cli/examples/goals_to_csv.py goals_0.json goals.csv

# Direct pipeline streaming via stdin
omi --json goal list --limit 200 | python sdks/python-cli/examples/goals_to_csv.py - goals.csv

# Combine multiple pages with automatic deduplication by goal ID
python sdks/python-cli/examples/goals_to_csv.py goals_0.json goals_200.json all_goals.csv --force
```

### CLI Options

| Argument | Description | Default |
|:---|:---|:---|
| `SOURCE ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `DESTINATION` | Destination path for the `.csv` file | *(required)* |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

## 3. CSV Columns and Sample Output

The exported CSV provides the following 10 structured fields:

1. `id` - Unique goal identifier.
2. `title` - Goal title or description.
3. `status` - Normalized status (`active`, `completed`, `archived`).
4. `goal_type` - Metric type (`numeric`, `scale`, `boolean`, `qualitative`).
5. `current_value` - Current recorded metric value.
6. `target_value` - Target milestone value.
7. `unit` - Metric unit (e.g., `sessions`, `books`, `pages`).
8. `progress_percentage` - Normalized completion progress (e.g., `50.00%`).
9. `created_at` - Goal creation timestamp (ISO 8601).
10. `updated_at` - Last update timestamp (ISO 8601).

### Sample CSV Row

```csv
id,title,status,goal_type,current_value,target_value,unit,progress_percentage,created_at,updated_at
0192e4a1-b847,Read 25 technical books,active,numeric,15,25,books,60.00%,2026-09-01T08:00:00Z,2026-09-20T10:00:00Z
```

## 4. Security & Spreadsheet Compatibility

- **Formula Injection (DDE) Protection**: Any string field starting with dangerous spreadsheet formula triggers (`=`, `+`, `-`, `@`) is safely escaped with a leading single quote (`'`), preventing malicious formula execution when opened in Excel or Calc.
- **UTF-8 BOM Header**: Includes `\xef\xbb\xbf` so Microsoft Excel automatically recognizes Unicode characters without requiring manual import wizards.
- **Automated Verification**: Run the automated test suite with:
  ```sh
  python sdks/python-cli/tests/test_goals_to_csv.py
  ```
