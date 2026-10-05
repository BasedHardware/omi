# Convert an action-item export to CSV

Use this recipe to review, filter, and import your Omi action items and tasks
into spreadsheet applications such as Microsoft Excel, Google Sheets, LibreOffice Calc,
or task managers like Notion and Asana. It reads saved JSON exports, makes no
network requests, and normalises timestamps and booleans. You need Python 3.10+
and an authenticated `omi-cli` for the initial export.

## Step 1: Export action items

Export up to 200 action items to a JSON file:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

To export only pending action items:

```sh
omi --json action-item list --open --limit 200 > action_items_open.json
```

## Step 2: Convert to CSV

Run the converter script [`action_items_to_csv.py`](action_items_to_csv.py) directly against the exported JSON (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/action_items_to_csv.py action_items_0.json -o action_items.csv
```

To open directly in Microsoft Excel on Windows without character encoding issues,
pass the `--excel` flag (adds a UTF-8 BOM):

```sh
python action_items_to_csv.py action_items_0.json -o action_items.csv --excel
```

You can also pipe the CLI output directly into the converter:

```sh
omi --json action-item list --limit 200 | python action_items_to_csv.py - -o action_items.csv
```

## CSV Columns

| Column | Description | Format |
|---|---|---|
| `id` | Unique task ID | Text |
| `description` | Task description | Sanitized text (formula-safe) |
| `completed` | Completion status | `true` or `false` |
| `due_at` | Task deadline | `YYYY-MM-DD HH:MM:SS` (UTC) |
| `created_at` | Task creation timestamp | `YYYY-MM-DD HH:MM:SS` (UTC) |
| `updated_at` | Last updated timestamp | `YYYY-MM-DD HH:MM:SS` (UTC) |
| `conversation_id` | Originating conversation ID | Text |

## Security & Reliability Invariants

- **Formula Injection Mitigation**: Any field beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` is escaped with a leading single quote (`'`) to protect spreadsheet users against DDE formula execution.
- **Atomic File Writing**: Writes via a temporary file before renaming, ensuring that the target file is never left in a partial or corrupt state.
- **Directory Traversal Protection**: Rejects relative paths containing `..` components.
- **RFC 4180 Compliance**: Uses standard Windows CRLF (`\r\n`) line terminations and minimal quoting.
