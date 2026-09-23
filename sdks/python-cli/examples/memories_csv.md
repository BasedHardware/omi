# Convert a memory-list export to CSV

Use this recipe to review captured memories, facts, and learned preferences
in a spreadsheet. It reads a saved JSON export, makes no network requests,
and runs on the Python standard library alone. It completes the export
trilogy alongside [`conversations_csv.md`](conversations_csv.md): the same
converter pattern, the same spreadsheet-safety rules, applied to the memory
list. You need Python 3.10+ and an authenticated `omi-cli` for the initial
export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot. `omi memory list` defaults to `--limit 25` and accepts up to
`--limit 200`; you can also filter server-side with `--categories
work,learnings`.

The converter is a committed script, `memories_to_csv.py`, in this directory:

```sh
python memories_to_csv.py memories.json memories.csv
```

Or pipe the export directly, using `-` for stdin:

```sh
omi --json memory list --limit 200 | python memories_to_csv.py - memories.csv
```

Import the result as UTF-8, comma-delimited text in Excel, Google Sheets,
Apple Numbers, or another spreadsheet application. The script writes UTF-8
with a BOM so desktop spreadsheet apps detect the encoding without prompting.
The converter preserves complete IDs, accents, quoted text, and embedded
newlines. Missing fields become empty cells; an empty list produces the column
header only. Tags are joined into one cell with `; ` separators. Boolean
fields render as `true` / `false`.

## Column reference

| Column | Source field | Notes |
| :--- | :--- | :--- |
| `id` | memory id | Full ID preserved, never truncated |
| `content` | the captured memory text | May contain newlines and quotes |
| `category` | e.g. `work`, `learnings`, `skills` | Server-side enum, plus any custom value |
| `visibility` | `private` or `public` | Defaults to `private` |
| `tags` | tag list | Joined with `; ` |
| `created_at` | creation timestamp | ISO 8601 as returned |
| `updated_at` | last-edit timestamp | ISO 8601 as returned |
| `manually_added` | user-created flag | `true` / `false` |
| `reviewed` | review flag | `true` / `false` |
| `edited` | edited-after-capture flag | `true` / `false` |

## Overwrite and failure behavior

The script refuses to overwrite an existing destination; pass `--force` to
replace it. A failed write leaves no partial file behind: the export is fully
formatted in memory before anything touches the filesystem, and `--force`
replacements go through an atomic rename. Input with a Windows PowerShell BOM
is accepted transparently.

## Spreadsheet security notes

Cells whose text starts with `=`, `+`, `-`, or `@` (or with a tab, carriage
return, or newline) are prefixed with an apostrophe so spreadsheet importers
do not evaluate them as formulas — the standard CSV-injection guard used
across the export trilogy. The apostrophe is intentional and may be visible in
some importers. For exact unmodified values, retain the source JSON.

Treat the exported file as private memory data: `content` can hold personal
facts, and most rows are `visibility: private`.
