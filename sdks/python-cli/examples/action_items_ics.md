# Export Omi Action Items to iCalendar (.ics)

Use this recipe to turn your Omi action items into a standard **iCalendar
(`.ics`)** file. Each action item with a due date becomes a `VTODO` task, so the
file imports cleanly into Google Calendar / Tasks, Apple Calendar & Reminders,
Microsoft Outlook, and any RFC 5545 compatible client.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` (`omi auth login`)

## Quickstart

### Option 1: Direct Pipeline via Stdin (Recommended)

```bash
omi --json action-item list | python action_items_to_ics.py - -o tasks.ics
```

### Option 2: Export from a Saved JSON File

1. Export action items to a local JSON file:
   ```bash
   omi --json action-item list > action_items.json
   ```

2. Convert them into a calendar file:
   ```bash
   python action_items_to_ics.py action_items.json -o tasks.ics
   ```

Then import `tasks.ics` into your calendar app of choice.

---

## What each task contains

For every action item:

- `SUMMARY` — the item description (or title).
- `DUE` — the due date, when `due_at` is present (UTC).
- `CREATED` — from `created_at`, when present.
- `STATUS` — `COMPLETED` (with `PERCENT-COMPLETE:100`) or `NEEDS-ACTION`.
- `UID` — stable, derived from the item `id` so re-imports update rather than
  duplicate.
- `X-OMI-CONVERSATION-ID` — the originating conversation id, when present.

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `input` | JSON file path, or `-` for stdin | (required) |
| `--output`, `-o` | Output `.ics` file path | `action_items.ics` |

## Notes on correctness

- Output uses **CRLF** line endings and **line folding** at 75 octets, per
  RFC 5545.
- Text values are escaped (`\\`, `;`, `,`, newlines) so descriptions with commas
  or semicolons import correctly.
- Timestamps are normalised to UTC (`...Z`). Items without a `due_at` are still
  exported as undated tasks.
- Input may be a single action-item object or a JSON array; files are read with
  UTF-8 BOM protection, and stdin is supported via `-`.
