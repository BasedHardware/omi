# Convert a memory export to an Excel workbook (.xlsx)

Use this recipe to review or filter memories in Excel — sort capture times,
AutoFilter by category/visibility, keep text safely typed. It reads one or
more `memory list` exports, makes no network requests, and writes one
`.xlsx` workbook.

Requires [`openpyxl`](https://pypi.org/project/openpyxl/):

```sh
pip install openpyxl
```

Export your memories:

```sh
omi --json memory list > memories.json
```

## The converter

The script lives at [`memories_to_xlsx.py`](memories_to_xlsx.py) in this
directory.

**Native cell types:**

* `created_at` / `updated_at` → **native datetime cells** (UTC,
  `yyyy-mm-dd hh:mm:ss`).
* `manually_added` / `reviewed` → **native boolean** (`TRUE`/`FALSE`).
* Every string is explicitly string-typed (`cell.data_type = 's'`) — a
  memory like `=SUM(A1)` is never executed as a formula.
* Columns: `id, content, category, tags, visibility, manually_added,
  reviewed, app_id, created_at (UTC), updated_at (UTC)`; `tags` joins with
  `|`, `app_id` falls back to `source_app`.
* **AutoFilter** on all columns + **frozen header** (`A2`); auto-sized
  widths.

## Usage

```sh
python memories_to_xlsx.py memories.json -o memories.xlsx
```

Multi-page — each memory ID appears once:

```sh
python memories_to_xlsx.py memories_p1.json memories_p2.json -o memories.xlsx
```

## Safety

* `..` in the `-o` path is refused.
* Existing files never overwritten — `.partial` + `os.replace` swap.
* Malformed JSON or missing input exits `2`.
