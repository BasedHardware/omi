# Convert a memory-list export to CSV

Use this recipe to review your saved memories, user facts, and learned preferences
in a spreadsheet. It reads a saved JSON export or stdin stream, makes no network
requests, and writes a spreadsheet-ready `.csv` file. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

---

## 1. Export memories from OMI CLI

Export your memories to a JSON file:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. Note that `--limit 200`
is one page and the CLI's maximum, not a complete-account backup. To retrieve another
page, increase `--offset` by 200 and save to a different file. Changes to the account
between requests can affect offset pagination.

---

## 2. Convert to CSV

Run `memories_to_csv.py` with the source JSON and target CSV paths:

```sh
python3 memories_to_csv.py memories.json memories.csv
```

Or pipe directly from `omi` without creating an intermediate file:

```sh
omi --json memory list | python3 memories_to_csv.py - memories.csv
```

Pass `--force` (`-f`) if you want to overwrite an existing CSV file:

```sh
python3 memories_to_csv.py memories.json memories.csv --force
```

---

## 3. CSV Schema

The generated spreadsheet includes the following columns:

| Column | Description | Example |
|---|---|---|
| `id` | Unique identifier of the memory | `mem_12345` |
| `content` | The memory text or captured fact | `Prefers dark roast coffee in the mornings` |
| `category` | Categorization tag | `lifestyle`, `work`, `habits`, `skills` |
| `created_at` | ISO 8601 creation timestamp | `2026-09-24T08:15:00Z` |
| `updated_at` | ISO 8601 last update timestamp | `2026-09-24T08:15:00Z` |
| `manually_added` | Boolean flag indicating manual entry | `false` |

---

## 4. Spreadsheet Import & Security

- **Formula Injection Defense:** Cells containing formula prefixes (`=`, `+`, `-`, `@`) are automatically escaped with a leading apostrophe (`'`) to prevent formula execution in Microsoft Excel, Google Sheets, and Apple Numbers.
- **UTF-8 with BOM:** Files are encoded in `utf-8-sig` so emojis and international characters display correctly when opened directly in desktop spreadsheet applications.
