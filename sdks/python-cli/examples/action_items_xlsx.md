# Convert action items export to an Excel workbook (.xlsx)

Export action items and task backlogs from Omi into an Excel workbook (`.xlsx`) with native cell types: `due_at`, `created_at`, and `updated_at` become UTC datetime cells for sorting and filtering, `completed` becomes a native boolean cell, the header row is frozen at `A2`, and AutoFilter is enabled across all columns.

This recipe reads offline JSON exports and makes no network requests. It complements [`action_items_sqlite.md`](action_items_sqlite.md), which stores tasks in a local SQLite database for SQL queries.

## Prerequisites

You need Python 3.10+, an authenticated `omi-cli`, and [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

## Step 1: Export action items to JSON

Export action items from the Omi CLI into a JSON file:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

To fetch multiple pages, increment `--offset` by 200:

```sh
omi --json action-item list --limit 200 --offset 200 > action_items_page2.json
```

## Step 2: Convert to Excel (.xlsx)

Run the converter script, passing one or more JSON files:

```sh
python action_items_to_xlsx.py action_items.json -o tasks.xlsx
```

To merge multiple paginated exports with automatic deduplication by task ID:

```sh
python action_items_to_xlsx.py action_items.json action_items_page2.json -o tasks.xlsx
```

To overwrite an existing destination file:

```sh
python action_items_to_xlsx.py action_items.json -o tasks.xlsx --overwrite
```

## Columns and Schema

The generated worksheet is named `action_items` and includes the following fields:

| Column | Header | Type in Excel | Description |
| :--- | :--- | :--- | :--- |
| 1 | `id` | Text | Unique action item identifier. |
| 2 | `description` | Text | Task description. Typed as text to protect against formula injection. |
| 3 | `completed` | Boolean | Native Excel boolean (`TRUE` / `FALSE`) for filtering. |
| 4 | `due_at (UTC)` | Datetime | Task deadline normalized to UTC (`yyyy-mm-dd hh:mm:ss`). |
| 5 | `created_at (UTC)` | Datetime | Creation timestamp normalized to UTC (`yyyy-mm-dd hh:mm:ss`). |
| 6 | `updated_at (UTC)` | Datetime | Last update timestamp normalized to UTC (`yyyy-mm-dd hh:mm:ss`). |
| 7 | `conversation_id` | Text | Associated conversation ID, if linked to a conversation. |

## Security & Reliability Guarantees

- **Formula Injection Mitigation**: Text cells explicitly set `cell.data_type = 's'`, ensuring spreadsheet software treats tasks starting with `=`, `+`, `-`, or `@` strictly as text literals without executing formulas.
- **Atomic File Writing**: Generates the workbook to a `.partial` file in the target directory before atomically renaming via `os.replace`, preventing partially written workbooks if execution is interrupted.
- **Path Traversal Protection**: Rejects paths containing `..` components to ensure files are written only within the intended directory hierarchy.
- **Auto-fit Columns & Usability**: Dynamically calculates column widths with padding up to 70 characters and locks the top header row with `freeze_panes = "A2"`.
- **Privacy Notice**: Treat the exported spreadsheet as private personal knowledge data.
