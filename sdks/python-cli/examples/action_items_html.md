# Recipe: Action Items → HTML Dashboard Report

Export your Omi action items to a self-contained, printable HTML dashboard — zero third-party dependencies, pure Python standard library.

## What you get

- A single `.html` file you can open in any browser or print to PDF
- Summary cards: **Total**, **Pending**, **Overdue**, **Completed**
- Color-coded status badges per task
- Due date normalization with optional timezone offset
- Automatic deduplication across multi-page JSON exports
- `@media print` rules for clean hard-copy output
- Safe atomic write (`xb` mode) — refuses to overwrite an existing file

## Prerequisites

```bash
pipx install omi-cli   # or: pip install omi-cli
export OMI_API_KEY="your_api_key"
```

## Step 1 — Export action items to JSON

Fetch your action items and save them as JSON:

```bash
# All items (open + completed)
omi --json action-item list > action_items_all.json

# If pagination is needed, repeat with --page:
omi --json action-item list --page 2 > action_items_page2.json
```

## Step 2 — Save the script

Download [`action_items_html.py`](action_items_html.py) from this directory, or copy it alongside your JSON exports.

## Step 3 — Run it

```bash
# Single file, UTC
python action_items_html.py action_items_all.json --output dashboard.html

# Multi-page export, Tokyo timezone
python action_items_html.py \
    action_items_page1.json \
    action_items_page2.json \
    --utc-offset +09:00 \
    --output dashboard_jp.html

# Eastern US
python action_items_html.py action_items_all.json \
    --utc-offset -05:00 \
    --output dashboard_et.html
```

Open the resulting file in any browser — or print / save as PDF via the browser's built-in print dialog.

## Output

The generated file is fully self-contained (no CDN, no external fonts, no tracking).

| Section | Details |
|---|---|
| Summary cards | Total · Pending · Overdue · Completed counts |
| Task table | Done mark · Task text · Status badge · Due date · Created date · Conversation ID |
| Print CSS | Clean hard-copy via browser Print → Save as PDF |

## Notes

- **Deduplication**: if the same task ID appears in multiple input files, it is counted once.
- **Due date detection**: reads `due_date` and `due_at` fields; items with no due date and not yet completed are treated as `pending`.
- **Overwrite protection**: uses Python's `'xb'` open mode — exits with a clear error rather than silently clobbering an existing report.
- **No network access**: all CSS is embedded inline; no external resources are referenced.

## Related recipes

- [Agent Quickstart](agent_quickstart.md) — run an Omi agent from the CLI
- [README](README.md) — full example index
