# Put your goals and milestones on a calendar (.ics)

Use this recipe to track your personal milestones, target deadlines, and long-term habits alongside your daily calendar meetings: it converts one or more `goal list` JSON exports into a standard RFC 5545 iCalendar (`.ics`) file compatible with Google Calendar, Apple Calendar, Microsoft Outlook, Thunderbird, and Apple Reminders.

It reads saved JSON exports, makes zero network requests, and supports dual calendar modes:
- **`vevent` (default)**: Visual milestone events scheduled at target deadlines with progress descriptions.
- **`vtodo`**: Native actionable task items featuring RFC 5545 `PERCENT-COMPLETE` progress bars for to-do managers and Reminders apps.

## Prerequisites

- Python 3.9+
- An authenticated `omi-cli` session (`omi auth login`)

## 1. Export your goals

Export your goals using the CLI:

```sh
omi --json goal list > goals.json
```

For large account collections spanning multiple pages, retrieve each page using `--offset`:

```sh
omi --json goal list --limit 100 --offset 0 > goals_page1.json
omi --json goal list --limit 100 --offset 100 > goals_page2.json
```

## 2. Convert to iCalendar (.ics)

Run `goals_to_ics.py` to create your calendar file:

```sh
python goals_to_ics.py goals.json -o goals.ics
```

### Direct terminal pipeline (streaming)

Stream directly from the Omi CLI through Unix pipes without intermediate files:

```sh
omi --json goal list | python goals_to_ics.py - -o goals.ics --force
```

### VTODO mode for Apple Reminders & Task Managers

To import your goals as actionable tasks with native completion percentages into Apple Reminders, OmniFocus, or Thunderbird Tasks, use `--mode vtodo`:

```sh
python goals_to_ics.py goals.json --mode vtodo -o goals_tasks.ics --force
```

### Multi-page aggregation and deduplication

When passing multiple files from paginated exports, `goals_to_ics.py` automatically merges records and deduplicates by `id`, keeping the newest `updated_at` entry:

```sh
python goals_to_ics.py goals_page1.json goals_page2.json -o full_calendar.ics --force
```

### Filtering and custom calendar name

```sh
# Only export active goals to a custom-named calendar
python goals_to_ics.py goals.json --status active --name "Q4 2026 Goals" -o q4_goals.ics
```

## Command line options

| Option | Default | Description |
| :--- | :--- | :--- |
| `sources` | _(required)_ | One or more input JSON file paths, or `-` for stdin. |
| `-o`, `--output` | `-` (stdout) | Destination path for the `.ics` output file. |
| `-f`, `--force` | `False` | Overwrite existing destination file if present. |
| `--mode` | `vevent` | Calendar component mode: `vevent` (calendar events) or `vtodo` (actionable tasks). |
| `--name` | `Omi Goals` | Custom calendar name (`X-WR-CALNAME`). |
| `--status` | `all` | Filter by status: `all`, `active`, `achieved`, `inactive`. |
| `--type` | `all` | Filter by goal type (e.g. `scale`, `numeric`, `boolean`, or `all`). |

## RFC 5545 compliance & security guarantees

1. **RFC 5545 Strict Compliance**: Outputs CRLF line endings (`\r\n`), folds long lines at 75 octets, and safely escapes backslashes, semicolons, commas, and newlines per RFC 5545 §3.3.11.
2. **Native Percentage Tracking**: In `vtodo` mode, maps continuous goal metrics to standard integer `PERCENT-COMPLETE` values (0–100).
3. **Path Traversal Protection**: Refuses any destination output path containing traversal segments (`..`) to safeguard local directories.
4. **Atomic Non-Destructive Writes**: Uses safe temporary-file writes and atomic renames to prevent partial files or accidental overwrites without `--force`.
5. **Air-Gapped & Offline**: 100% standard library code; executes locally with zero external network dependencies.
