# Export Omi Conversations to a Self-Contained HTML Report

Use this recipe to turn your Omi conversation exports into a single, styled
**HTML report** you can open in any browser, share, or archive. The output is
one self-contained `.html` file with inline CSS (no external assets), so it
works completely offline. All transcript and summary text is HTML-escaped, so
content can never inject markup or scripts into the report.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` (`omi auth login`)

## Quickstart

### Option 1: Direct Pipeline via Stdin (Recommended)

```bash
omi --json conversation list --include-transcript --limit 50 | python conversations_to_html.py - -o report.html
```

### Option 2: Export from a Saved JSON File

1. Export conversations to a local JSON file:
   ```bash
   omi --json conversation list --include-transcript --limit 100 > conversations.json
   ```

2. Convert the JSON export into a single HTML report:
   ```bash
   python conversations_to_html.py conversations.json -o report.html
   ```

### Option 3: Export a Single Specific Conversation

```bash
omi --json conversation get <CONVERSATION_ID> --include-transcript > conversation.json
python conversations_to_html.py conversation.json -o report.html
```

---

## What the report contains

For each conversation:

- **Title**, with category / source / date badges.
- **Summary** (from `structured.overview`), when present.
- **Action Items** rendered as a checklist (checked / unchecked boxes).
- **Transcript**, with per-segment speaker labels and `[MM:SS]` timestamps.

The document adapts to light/dark mode automatically via
`prefers-color-scheme`.

## Input shape

The script accepts either a single conversation object or a JSON array of
conversations — the same shape produced by `omi --json conversation list`.
Files are read with UTF-8 BOM protection; stdin is supported via `-`.

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `input` | JSON file path, or `-` for stdin | (required) |
| `--output`, `-o` | Output HTML file path | `conversations_report.html` |

## Security note

Every dynamic value (titles, overviews, action items, transcript text,
speaker labels, timestamps) is passed through `html.escape(..., quote=True)`
before being written. A transcript containing `<script>...</script>` is
rendered as visible, inert text rather than executed, so opening the report is
safe even for untrusted conversation content.
