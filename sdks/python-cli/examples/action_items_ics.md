# Put Open Action Items on Your Calendar (.ics)

Use this recipe to see Omi action items next to your meetings and daily agenda: it converts one or more
`action-item list` JSON exports into a standard iCalendar (`.ics`) file conforming to RFC 5545. Applications
such as **Google Calendar**, **Apple Calendar**, **Microsoft Outlook**, and **Mozilla Thunderbird** can
subscribe to or import the generated calendar.

Each action item with a `due_at` timestamp becomes a calendar event starting at its scheduled time with an
informative summary, status indicator (`CONFIRMED` or `COMPLETED`), and originating conversation metadata.
Items without a due date are skipped and reported.

---

## Prerequisites

You need Python 3.10+ and an authenticated `omi-cli` installed:

```sh
pip install omi-cli
omi auth login
```

Export your action items (up to 200 items per batch):

```sh
omi --json action-item list --limit 200 > action_items.json
```

Verify that the export file was populated before running the converter. This is one page; to retrieve more,
re-run with `--offset 200` (and so on) into separate files (e.g. `p1.json p2.json`) and pass them together.
The converter deduplicates items by their ID.

---

## Quickstart

### 1. Direct Pipeline Stream (Stdout)

Generate the iCalendar stream directly from the CLI output:

```sh
set -o pipefail
omi --json action-item list --limit 200 | python action_items_to_ics.py -
```

### 2. Export to a Dedicated Calendar File

Write the `.ics` file for calendar import:

```sh
python action_items_to_ics.py action_items.json -o ~/Calendars/omi_tasks.ics
```

### 3. Filter to Open Tasks with Custom Duration

Export only open, uncompleted tasks and assign a 60-minute duration block to each:

```sh
python action_items_to_ics.py action_items.json --status open --event-length 60 -o pending_tasks.ics
```

### 4. Custom Calendar Name

Specify the calendar name that appears in your calendar application:

```sh
python action_items_to_ics.py action_items.json --calendar-name "Work Sprints" -o work.ics
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more JSON export files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Destination `.ics` file path | `stdout` |
| `--status` | `--status` | Filter items: `all`, `open`, or `completed` | `all` |
| `--event-length` | `--event-length` | Event duration in minutes for scheduled tasks | `30` |
| `--calendar-name` | `--calendar-name` | Calendar display name (`X-WR-CALNAME`) | `"Omi Action Items"` |
| `--overwrite` | `--overwrite` | Allow overwriting existing destination files | `False` |

---

## Calendar Output Preview

Here is an example of the generated iCalendar format:

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//omi-cli examples//action_items_to_ics//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Omi Action Items
BEGIN:VEVENT
UID:omi-action-act_02_open@omi-cli
DTSTAMP:20261002T070000Z
DTSTART:20261001T100000Z
DTEND:20261001T103000Z
SUMMARY:Fix memory leak in background worker
DESCRIPTION:Omi action item: act_02_open\nConversation: conv_991
STATUS:CONFIRMED
CATEGORIES:Omi
CREATED:20260928T090000Z
END:VEVENT
END:VCALENDAR
```

---

## Calendar Import Workflows

### Google Calendar
1. Open Google Calendar and go to **Settings > Import & export**.
2. Select your exported `omi_tasks.ics` file and choose the destination calendar.

### Apple Calendar
1. Open Calendar on macOS and choose **File > Import...** (or press `Cmd+O`).
2. Select the exported `.ics` file and choose a calendar list.

### Outlook / Thunderbird
1. In Outlook, navigate to **File > Open & Export > Open Calendar (.ics)**.
2. In Thunderbird, select **Events and Tasks > Import...** and pick the `.ics` file.

Because UIDs are deterministically derived from action item IDs, re-importing updated exports updates existing
entries rather than creating duplicates.

---

## Design Principles

- **Zero Third-Party Dependencies**: Pure Python standard library (`argparse`, `datetime`, `json`, `pathlib`).
- **RFC 5545 Conformance**: Strict 75-octet line folding without splitting multi-byte UTF-8 sequences.
- **RFC 5545 §3.3.11 Text Escaping**: Automatically escapes backslashes, semicolons, commas, and line breaks.
- **Safe POSIX Permissions**: Creates output files with standard user permissions (`0644`).
- **Atomic File Operations**: Uses temporary file replacement when `--overwrite` is specified.
- **Piped Stream Hygiene**: Native `BrokenPipeError` signal handling for commands like `| head`.
