# Export Omi Memories to CSV

Use this recipe to turn a `memory list` JSON export into a spreadsheet-ready
CSV file: one row per memory with id, content, category, tags, visibility,
timestamps, and source app — ready for Excel, Google Sheets, pandas, or any
import pipeline. The converter is stdlib-only, makes no network requests, and
guards cells against formula injection when the CSV is opened in a spreadsheet.

## Requirements

- Python 3.10+ (stdlib only — no `pip install` needed)
- An authenticated `omi-cli` (`omi auth login`) for the initial export

## Quickstart

### Option 1: Pipe straight from the CLI

`memory list` defaults to 25 records, so pass `--limit 200` explicitly; page
with `--offset` for larger accounts.

```bash
omi --json memory list --limit 200 | python memories_to_csv.py - -o memories.csv
omi --json memory list --limit 200 --offset 200 | python memories_to_csv.py - -o memories_2.csv
```

### Option 2: From a saved JSON export

```bash
omi --json memory list --limit 200 > memories.json
python memories_to_csv.py memories.json -o memories.csv
```

### Option 3: Print to stdout (pipe into another tool)

Stdout CSV is plain UTF-8 without the BOM (friendlier for downstream text
tools); only `-o` files carry the BOM for Excel.

```bash
omi --json memory list --limit 200 | python memories_to_csv.py -
```

### Option 4: Filter by category or visibility

```bash
omi --json memory list | python memories_to_csv.py - --category work,learnings -o work_memories.csv
omi --json memory list | python memories_to_csv.py - --visibility private -o private_memories.csv
```

## Columns

`id`, `content`, `category`, `tags`, `visibility`, `created_at`, `updated_at`, `app_id`

- `tags` renders as a pipe-joined list (`focus|q4`).
- `created_at`/`updated_at` are normalized to ISO-8601 UTC; unusable values
  are kept raw instead of crashing the export.
- Missing fields render as empty cells.
- `app_id` falls back to the legacy `source_app` field when present.

## Robustness Guarantees

- **UTF-8 BOM** — the file opens correctly in Excel by default.
- **Formula-injection guard** — cells starting with `=`, `+`, `-`, `@` (or a
  tab/CR/LF) are prefixed with an apostrophe so a stored memory cannot execute
  as a spreadsheet formula.
- **Loose row coercion** — one odd record (a string, a number, a `None` row)
  is skipped; it cannot crash the export, filtered or not.
- **Envelope unwrapping** — accepts bare arrays, `{"memories": [...]}`,
  `{"items": ...}`, `{"data": ...}`, or a single memory object; error payloads
  like `{"detail": "..."}` yield a header-only CSV.
- **Exclusive creation** — `-o` refuses to overwrite an existing file, and the
  complete CSV is built before opening the file, so conversion failures cannot
  leave a truncated CSV behind. A write error mid-file removes the partial
  output and reports a clean error.
- **BOM-tolerant input** — saved exports from editors that add a BOM and piped
  stdin both work.
