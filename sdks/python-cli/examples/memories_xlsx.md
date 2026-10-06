# Convert a memory-list export to an Excel workbook (.xlsx)

Use this recipe when you want your Omi memories, facts, and learnings in Microsoft
Excel, Apple Numbers, LibreOffice Calc, or Google Sheets with native spreadsheet cell
types: `created_at` and `updated_at` become real datetime cells you can sort and
filter in UTC, boolean flags (`manually_added`, `reviewed`) stay native booleans,
the header row is styled and frozen, and an AutoFilter is automatically enabled.
It reads a saved JSON export, makes no network requests, and complements
[`memories_markdown.md`](memories_markdown.md) when spreadsheet analysis and tabular
filtering are desired.

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and
[`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

## Step 1: Export memories

Export up to 200 memories (the maximum page size supported by `memory list`):

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This represents one page.
To retrieve subsequent pages, increase `--offset` by 200 and save to a new filename:

```sh
omi --json memory list --limit 200 --offset 200 > memories_200.json
```

## Step 2: Convert to Excel

Run the converter script [`memories_to_xlsx.py`](memories_to_xlsx.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/memories_to_xlsx.py memories_0.json -o memories.xlsx
```

To overwrite an existing spreadsheet:

```sh
python sdks/python-cli/examples/memories_to_xlsx.py memories_0.json -o memories.xlsx --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_xlsx.py - -o memories.xlsx
```

## Spreadsheet Structure & Columns

| Column | Cell Type | Formatting / Behavior |
|---|---|---|
| `id` | String (`s`) | Retains leading zeros; never coerced to numeric. |
| `category` | String (`s`) | Memory category (e.g. `work`, `learning`, `personal`). |
| `content` | String (`s`) | Formula injection protected; values like `=SUM(...)` remain literal text. |
| `tags` | String (`s`) | Comma-separated tags (e.g. `career, goals`). |
| `visibility` | String (`s`) | Visibility level (`private` or `public`). |
| `created_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `updated_at (UTC)` | Datetime | Native Excel datetime (`yyyy-mm-dd hh:mm:ss`) converted to UTC. |
| `manually_added` | Boolean | Native Excel boolean (`TRUE` / `FALSE`). |
| `reviewed` | Boolean | Native Excel boolean (`TRUE` / `FALSE`). |

## Security & Reliability Invariants

- **Formula Injection Mitigation**: Text cells explicitly set `cell.data_type = 's'`, ensuring that spreadsheet software treats notes and content beginning with `=`, `+`, `-`, or `@` strictly as text literals without executing formulas.
- **Atomic File Writing**: Generates the workbook to a `.partial` file in the target directory before atomically renaming via `os.replace`, preventing partially written workbooks if execution is interrupted.
- **Path Traversal Protection**: Rejects paths with `..` components to ensure files are written only within the intended directory hierarchy.
- **Auto-fit Columns & Usability**: Computes column width dynamically with padding up to 70 characters and locks the top header row with `freeze_panes = "A2"`.
- **Privacy Notice**: Treat the exported spreadsheet as private personal knowledge data.
