# Export memories to Tab-Separated Values (TSV)

Use this recipe to convert Omi memories, facts, and learnings into Tab-Separated Values (TSV). TSV files are ideal for fast copy-pasting directly into spreadsheet software (Microsoft Excel, Google Sheets, LibreOffice Calc) or web databases (Airtable, Notion table views) without comma-quoting or delimiter corruption.

It includes automatic formula injection escaping (`=`, `+`, `-`, `@`), whitespace and line break sanitation, and category filtering.

## Exporting Memories

Fetch memories with `omi-cli`:

```bash
omi --json memory list --limit 200 > memories.json
```

Or pipe directly into the converter:

```bash
omi --json memory list | python memories_to_tsv.py - -o memories.tsv
```

## Running the Exporter

Convert saved JSON exports to TSV:

```bash
python memories_to_tsv.py memories.json -o memories.tsv
```

Export specific categories only:

```bash
python memories_to_tsv.py memories.json -o work_memories.tsv --category work,skills
```

Merge multiple page files:

```bash
python memories_to_tsv.py page1.json page2.json -o all_memories.tsv
```

## Direct Clipboard Copying (Mac / Linux / Windows)

You can pipe TSV output directly to your system clipboard for instant pasting into spreadsheet software:

- **macOS:**
  ```bash
  python memories_to_tsv.py memories.json | pbcopy
  ```
- **Linux (X11):**
  ```bash
  python memories_to_tsv.py memories.json | xclip -selection clipboard
  ```
- **Windows (PowerShell):**
  ```powershell
  python memories_to_tsv.py memories.json | Set-Clipboard
  ```
