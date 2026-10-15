# Put Your Conversation History on a Calendar (.ics)

Use this recipe to see when Omi conversations occurred alongside your daily meetings and calendar events.
It converts one or more `conversation list` JSON exports into a standard iCalendar (`.ics`) file conforming
to RFC 5545. Applications like **Google Calendar**, **Apple Calendar**, **Microsoft Outlook**, and
**Mozilla Thunderbird** can subscribe to or import the generated calendar.

Each conversation with a `started_at` timestamp becomes a calendar event spanning `started_at` through
`finished_at` (or a configurable default length, such as 30 minutes, if `finished_at` is missing).
Transcripts are not exported to preserve privacy; titles, categories, folders, and sources are embedded.

---

## Prerequisites

You need Python 3.10+ and an authenticated `omi-cli` installed:

```sh
pip install omi-cli
omi auth login
```

Export your conversations (up to 200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
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
omi --json conversation list --limit 200 | python conversations_to_ics.py -
```

### 2. Export to a Dedicated Calendar File

Write the `.ics` file for calendar import:

```sh
python conversations_to_ics.py conversations.json -o ~/Calendars/omi_conversations.ics
```

### 3. Filter by Category with Custom Duration

Export only conversations belonging to the `work` category and apply a 45-minute default block:

```sh
python conversations_to_ics.py conversations.json --category work --default-length 45 -o work_sessions.ics
```

### 4. Custom Calendar Name

Specify the calendar name that appears in your calendar application:

```sh
python conversations_to_ics.py conversations.json --calendar-name "Executive Syncs" -o syncs.ics
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more JSON export files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Destination `.ics` file path | `stdout` |
| `--category` | `--category` | Filter conversations by category (case-insensitive) | `None` |
| `--default-length` | `--default-length` | Duration in minutes when `finished_at` is missing | `30` |
| `--calendar-name` | `--calendar-name` | Calendar display name (`X-WR-CALNAME`) | `"Omi Conversations"` |
| `--overwrite` | `--overwrite` | Allow overwriting existing destination files | `False` |

---

## Calendar Output Preview

Here is an example of the generated iCalendar format:

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//omi-cli examples//conversations_to_ics//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Omi Conversations
BEGIN:VEVENT
UID:omi-conversation-conv_01@omi-cli
DTSTAMP:20261002T070000Z
DTSTART:20261001T090000Z
DTEND:20261001T094500Z
SUMMARY:Quarterly Planning\; Strategy\, & Review
DESCRIPTION:Omi conversation: conv_01\nCategory: work\nFolder: Planning
STATUS:CONFIRMED
CATEGORIES:Omi\,work
END:VEVENT
END:VCALENDAR
```

---

## Calendar Import Workflows

### Google Calendar
1. Open Google Calendar and go to **Settings > Import & export**.
2. Select your exported `omi_conversations.ics` file and choose the target calendar.

### Apple Calendar
1. Open Calendar on macOS and choose **File > Import...** (or press `Cmd+O`).
2. Select the exported `.ics` file and choose a calendar list.

### Outlook / Thunderbird
1. In Outlook, navigate to **File > Open & Export > Open Calendar (.ics)**.
2. In Thunderbird, select **Events and Tasks > Import...** and pick the `.ics` file.

Event UIDs are deterministically derived from conversation IDs (`omi-conversation-{id}@omi-cli`), ensuring
that re-importing updated exports updates existing calendar entries without duplicating them.

---

## Design Principles

- **Zero Third-Party Dependencies**: Pure Python standard library (`argparse`, `datetime`, `json`, `pathlib`).
- **RFC 5545 Conformance**: Strict 75-octet line folding without splitting multi-byte UTF-8 sequences.
- **RFC 5545 §3.3.11 Text Escaping**: Automatically escapes backslashes, semicolons, commas, and line breaks.
- **Safe POSIX Permissions**: Creates output files with standard user permissions (`0644`).
- **Atomic File Operations**: Uses temporary file replacement when `--overwrite` is specified.
- **Piped Stream Hygiene**: Native `BrokenPipeError` signal handling for commands like `| head`.
