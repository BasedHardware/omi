# Export action items to Tab-Separated Values (TSV)

Use this recipe to convert Omi action items and task lists into Tab-Separated Values (TSV). TSV files are ideal for fast copy-pasting directly into spreadsheet software (Microsoft Excel, Google Sheets, LibreOffice Calc) or web databases (Airtable, Notion table views) without comma-quoting or delimiter corruption.

It includes automatic formula injection escaping (`=`, `+`, `-`, `@`), whitespace and line break sanitation, and status filtering.

## Exporting Action Items

Fetch action items with `omi-cli`:

```bash
omi --json action-item list --limit 200 > action_items.json
```

Or pipe directly into the converter:

```bash
omi --json action-item list | python action_items_to_tsv.py - -o tasks.tsv
```

## Running the Exporter

Convert saved JSON exports to TSV:

```bash
python action_items_to_tsv.py action_items.json -o tasks.tsv
```

Export open / pending tasks only:

```bash
python action_items_to_tsv.py action_items.json -o open_tasks.tsv --status open
```

Merge multiple page files:

```bash
python action_items_to_tsv.py page1.json page2.json -o all_tasks.tsv
```

## Direct Clipboard Copying (Mac / Linux / Windows)

You can pipe TSV output directly to your system clipboard for instant pasting into spreadsheet software:

- **macOS:**
  ```bash
  python action_items_to_tsv.py action_items.json | pbcopy
  ```
- **Linux (X11):**
  ```bash
  python action_items_to_tsv.py action_items.json | xclip -selection clipboard
  ```
- **Windows (PowerShell):**
  ```powershell
  python action_items_to_tsv.py action_items.json | Set-Clipboard
  ```
