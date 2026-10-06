# Convert a goals export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi goals and targets in Microsoft Excel,
Apple Numbers, LibreOffice Calc, or Google Sheets with native spreadsheet cell
types: numeric target/current values, computed progress percentages, real
datetime cells for `created_at` and `updated_at`, formatted active status, styled
and frozen header row, and an AutoFilter automatically enabled. It reads a saved
JSON export, makes no network requests, and complements the CLI tools when rich
spreadsheet reporting is desired.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

## Step 1: Export goals

Export active goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Or export both active and inactive goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals_all.json
```

> **Note**: Unlike `memory` or `conversation`, `goal list` accepts `--limit` and
> `--include-inactive` (it does not use `--offset`).

## Step 2: Convert to Excel

Run the converter script [`goals_to_xlsx.py`](goals_to_xlsx.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/goals_to_xlsx.py goals.json -o goals.xlsx
```

To overwrite an existing spreadsheet:

```sh
python sdks/python-cli/examples/goals_to_xlsx.py goals.json -o goals.xlsx --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json goal list --limit 100 | python sdks/python-cli/examples/goals_to_xlsx.py - -o goals.xlsx
```

## Spreadsheet Structure & Columns

| Column | Cell Type | Formatting / Behavior |
|---|---|---|
| `id` | String (`s`) | Retains leading zeros; never coerced to numeric. |
| `title` | String (`s`) | Formula injection protected; values like `=SUM(...)` remain literal text. |
| `goal_type` | String (`s`) | Goal classification (`boolean`, `scale`, `numeric`). |
| `current_value` | Number | Numeric current progress value. |
| `target_value` | Number | Numeric target threshold. |
| `unit` | String (`s`) | Measurement unit (e.g. `hours`, `pages`, or empty). |
| `progress_pct` | Number | Calculated completion percentage bounded to `0.0` to `100.0` (numeric value, e.g. `75.0` for 75%). |
| `is_active` | String (`s`) | Normalized goal status string (`active` or `inactive`). |
| `created_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `updated_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |

## Security & Reliability Invariants

- **Formula Injection Mitigation**: Text cells explicitly set `cell.data_type = 's'`, ensuring that spreadsheet software treats titles beginning with `=`, `+`, `-`, or `@` strictly as text literals without executing formulas.
- **Progress Normalization**: Safely handles scale goals `(current - min) / (max - min)`, numeric goals `current / target`, and boolean goals `100.0%` or `0.0%`, protecting against division by zero.
- **Atomic File Writing**: Generates the workbook to a `.partial` file in the target directory before atomically renaming via `os.replace`, preventing partially written workbooks if execution is interrupted.
- **Path Traversal Protection**: Rejects paths with `..` components to ensure files are written only within the intended directory hierarchy.
- **Auto-fit Columns & Usability**: Computes column width dynamically with padding up to 60 characters and locks the top header row with `freeze_panes = "A2"`.
