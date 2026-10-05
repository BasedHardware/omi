# Convert an action-item export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi tasks and action items in Microsoft Excel,
Apple Numbers, LibreOffice Calc, or Google Sheets with native spreadsheet cell
types: `due_at`, `created_at`, and `updated_at` become real datetime cells you
can sort and filter, status is normalized to `completed` or `open`, the header
row is styled and frozen, and an AutoFilter is automatically enabled. It reads a
saved JSON export, makes no network requests, and complements
[`action_items_csv.md`](action_items_csv.md) when rich formatting is desired.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

## Step 1: Export action items

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Or export only pending items:

```sh
omi --json action-item list --open --limit 200 > action_items_open.json
```

## Step 2: Convert to Excel

Run the converter script [`action_items_to_xlsx.py`](action_items_to_xlsx.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/action_items_to_xlsx.py action_items_0.json -o action_items.xlsx
```

To overwrite an existing spreadsheet:

```sh
python sdks/python-cli/examples/action_items_to_xlsx.py action_items_0.json -o action_items.xlsx --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json action-item list --limit 200 | python sdks/python-cli/examples/action_items_to_xlsx.py - -o action_items.xlsx
```

## Spreadsheet Structure & Columns

| Column | Cell Type | Formatting / Behavior |
|---|---|---|
| `id` | String (`s`) | Retains leading zeros; never coerced to numeric. |
| `description` | String (`s`) | Formula injection protected; values like `=SUM(...)` remain literal text. |
| `completed` | String (`s`) | Normalized to `completed` or `open`. |
| `due_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `created_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `updated_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `conversation_id` | String (`s`) | Associated conversation identifier. |

## Security & Reliability Invariants

- **Formula Injection Mitigation**: Text cells explicitly set `cell.data_type = 's'`, ensuring that spreadsheet software treats descriptions beginning with `=`, `+`, `-`, or `@` strictly as text literals without executing formulas.
- **Atomic File Writing**: Generates the workbook to a `.partial` file in the target directory before atomically renaming via `os.replace`, preventing partially written workbooks if execution is interrupted.
- **Path Traversal Protection**: Rejects paths with `..` components to ensure files are written only within the intended directory hierarchy.
- **Auto-fit Columns & Usability**: Computes column width dynamically with padding up to 60 characters and locks the top header row with `freeze_panes = "A2"`.
