# Convert a goal export to CSV

Use this recipe to review or analyze goals in a spreadsheet or pipeline.
It reads a saved JSON export, makes no network requests, and emits UTF-8
CSV with a BOM so Excel and Google Sheets open it correctly. You need
Python 3.9+ and an authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list > goals.json
```

## The converter

The script lives at [`goals_to_csv.py`](goals_to_csv.py) in this directory —
stdlib-only, zero external dependencies. Fixed columns:

```
id, title, category, goal_type, current_value, target_value, unit,
progress_pct, is_active, created_at
```

* `progress_pct` is the completion percentage toward target — blank for
  qualitative goals or a `target_value` of `0`.
* `is_active` exports as `1`/`0`.
* `created_at` normalizes to ISO-8601 UTC; unparseable values keep raw text.
* Cells starting with `=`, `+`, `-`, `@`, tab, CR, or LF get a leading
  apostrophe — the formula-injection guard shared with the other CSV
  recipes — so a title that looks like a formula stays inert.

## Usage

Convert to a file (exclusive-create — never overwrites):

```sh
python goals_to_csv.py goals.json -o goals.csv
```

Stream to stdout:

```sh
omi --json goal list | python goals_to_csv.py | column -t -s,
```

Filter by type or status (comma-separated, case-insensitive):

```sh
python goals_to_csv.py goals.json --type numeric --status active -o active.csv
```

## Input tolerance

Unwraps `{"goals": [...]}`, `{"items": ...}`, `{"data": ...}`, a bare array,
or a single object; accepts UTF-8 BOM input; error payloads yield an empty
export.

## Safety

* `-o` refuses to overwrite; a write error removes the partial file.
* Exit code `2` signals any input/output failure.

## pandas ingestion

```python
import pandas as pd
df = pd.read_csv("goals.csv")
```
