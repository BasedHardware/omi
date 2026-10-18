# Convert a memory-list export to CSV

Use this recipe to review or migrate memories in a spreadsheet or pipeline.
It reads a saved JSON export, makes no network requests, and emits UTF-8 CSV
with a BOM so Excel and Google Sheets open it correctly. You need Python
3.10+ and an authenticated `omi-cli` for the initial export.

Export your memories:

```sh
omi --json memory list > memories.json
```

Check that the command succeeded before converting the file. This is the
current list, not a historical archive — re-export when the account changes.

## The converter

The script lives at [`memories_to_csv.py`](memories_to_csv.py) in this
directory — stdlib-only, no third-party packages. Fixed columns:

```
id, content, category, tags, visibility, created_at, updated_at, app_id
```

* `tags` joins multiple tags with `|`.
* `created_at`/`updated_at` normalize to ISO-8601 UTC (`...Z`); unparseable
  or boundary-overflow values keep their raw text rather than aborting.
* `app_id` falls back to `source_app` when the export carries that name.
* Cells starting with `=`, `+`, `-`, `@`, tab, CR, or LF get a leading
  apostrophe — the same formula-injection guard the conversations CSV recipe
  ships — so a memory that looks like a spreadsheet formula stays inert.
* Output carries a UTF-8 BOM so Excel/Sheets render non-ASCII text correctly.

## Usage

Convert a saved export to a file (exclusive-create — never overwrites):

```sh
python memories_to_csv.py memories.json -o memories.csv
```

Stream straight to stdout for a pipeline:

```sh
omi --json memory list | python memories_to_csv.py | python -c 'import csv,sys; print(sum(1 for _ in csv.reader(sys.stdin)))'
```

Filter by category or visibility (comma-separated, case-insensitive —
parity with the Markdown recipe):

```sh
python memories_to_csv.py memories.json --category work,learnings --visibility public -o work_memories.csv
```

## Input tolerance

The reader unwraps every CLI export shape — `{"memories": [...]}`,
`{"items": ...}`, `{"data": ...}`, a bare array, or a single object —
accepts UTF-8 BOM input, and treats error payloads (`{"error": ...}`) as an
empty export rather than a phantom row.

## Output guarantees

* **Atomic-ish `-o` writes.** The complete CSV is rendered before the
  filesystem is touched; the destination is opened exclusively and a write
  error removes the partial file. Exit code `2` signals any failure.
* **One odd row cannot kill the export.** Non-dict records are dropped;
  `dict`/`list`/numeric values coerce to spreadsheet-safe text.

## Spreadsheet / pandas ingestion

```python
import pandas as pd
df = pd.read_csv("memories.csv")
```
