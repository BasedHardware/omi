# Convert a memory export to CSV

Convert Omi memories JSON exports into clean, formatted CSV spreadsheets compatible with Microsoft Excel, Google Sheets, Apple Numbers, and Pandas.

## What this recipe does
- Exports all memory fields (`id`, `category`, `content`, `tags`, `visibility`, `is_user_created`, `created_at`, `updated_at`).
- Sanitizes formula injection characters (`=`, `+`, `-`, `@`) to protect spreadsheets against CSV injection attacks.
- Supports both direct JSON lists and API envelopes (`{"memories": [...]}`).
- Encodes output in UTF-8 with BOM (`utf-8-sig`) so characters and symbols display correctly in Excel without manual import wizard configuration.
- Optional category and tag filtering.

## Quick start

Export memories and pipe directly to CSV:

```sh
omi --json memory list --limit 200 | python memories_to_csv.py - -o memories.csv
```

Or convert an existing exported file:

```sh
python memories_to_csv.py memories.json -o memories.csv
```

Filter by specific categories:

```sh
python memories_to_csv.py memories.json --category work,learnings -o work_learnings.csv
```

Filter by tag:

```sh
python memories_to_csv.py memories.json --tag python,ai -o tech_memories.csv
```

Print CSV directly to stdout (useful for piping into `column -t -s,` or command line tools):

```sh
python memories_to_csv.py memories.json
```

## Spreadsheet Columns

| Column | Description |
|---|---|
| `id` | Unique memory identifier |
| `category` | Category classification (`work`, `learnings`, `skills`, `interests`, etc.) |
| `content` | Captured memory text and knowledge |
| `tags` | Comma-delimited list of tags |
| `visibility` | Memory visibility (`public`, `private`) |
| `is_user_created` | `true` if manually created, `false` if auto-extracted |
| `created_at` | Creation timestamp |
| `updated_at` | Last updated timestamp |

## Excel and Google Sheets Import

Because output files are written using `utf-8-sig`, double-clicking the generated `.csv` file opens it immediately in Excel with correct formatting. In Google Sheets, select **File > Import > Upload** and choose **Replace current sheet**.
