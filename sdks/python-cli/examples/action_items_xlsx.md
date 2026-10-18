# Convert an action-item export to an Excel workbook (.xlsx)

Use this recipe to work with action items in Excel — sort due dates
chronologically, filter completion status with AutoFilter, keep text safely
typed. It reads one or more `action-item list` exports, makes no network
requests, and writes one `.xlsx` workbook.

Requires [`openpyxl`](https://pypi.org/project/openpyxl/) — the only
non-stdlib piece (matching the conversations XLSX recipe):

```sh
pip install openpyxl
```

Export your action items:

```sh
omi --json action-item list --limit 500 > action_items.json
```

## The converter

The script lives at [`action_items_to_xlsx.py`](action_items_to_xlsx.py) in
this directory.

**Native cell types** — the columns Excel cares about land as real types:

* `due_at` / `created_at` / `updated_at` → **native datetime cells** (UTC,
  `yyyy-mm-dd hh:mm:ss`) — sortable chronologically, groupable by
  month/week.
* `completed` → **native boolean** (`TRUE`/`FALSE`) — filterable instantly.
* Every string is explicitly string-typed (`cell.data_type = 's'`) — a
  description like `=SUM(A1)` is never executed as a formula.
* Columns: `id, description, completed, due_at (UTC), created_at (UTC),
  updated_at (UTC), conversation_id, source`.
* **AutoFilter** on all columns + **frozen header** (`A2`); column widths
  auto-size to content.

## Usage

```sh
python action_items_to_xlsx.py action_items.json -o action_items.xlsx
```

Multi-page: feed several export files — each action-item ID appears once
even if it lands on multiple pages:

```sh
python action_items_to_xlsx.py action_items_p1.json action_items_p2.json -o action_items.xlsx
```

## Input tolerance

Unwraps `{"action_items": [...]}`, `{"items": ...}`, `{"data": ...}`, a bare
array, or a single object; accepts UTF-8 BOM input; non-dict records are
dropped.

## Safety

* `..` in the `-o` path is refused.
* Existing files are never overwritten — the write goes to a
  `<name>.partial` file then `os.replace` swaps it in, so a failed save
  leaves no truncated workbook.
* Malformed JSON or a missing input exits `2` with a clean message.
