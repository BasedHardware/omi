# Put your goals and milestones on a calendar (.ics)

Use this recipe to track your Omi goals, milestones, and OKRs directly in your calendar app (Google Calendar, Apple Reminders/Calendar, Microsoft Outlook, or Thunderbird).

It reads saved JSON exports or piped input via `stdin`, makes zero network requests, and generates a standard RFC 5545 `.ics` file. Goals are formatted as standard `VTODO` components with `PERCENT-COMPLETE` progress attributes (0–100%), status flags (`NEEDS-ACTION` / `COMPLETED`), target milestone dates (`DUE`), and reminder alarms (`VALARM`). You can also export goals as all-day milestone events (`VEVENT`).

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli`

## 1. Export your goals

Export your goals (up to 200 per page):

```sh
omi --json goal list --limit 200 --offset 0 > goals_0.json
```

If you have more than 200 goals, retrieve subsequent pages into separate files:

```sh
omi --json goal list --limit 200 --offset 200 > goals_200.json
```

## 2. Generate the iCalendar file

Run the companion converter script [`goals_to_ics.py`](goals_to_ics.py):

```sh
# Basic export as standard VTODO items (compatible with Apple Reminders, Outlook Tasks, Thunderbird)
python sdks/python-cli/examples/goals_to_ics.py goals_0.json goals.ics

# Direct pipeline streaming via stdin
omi --json goal list --limit 200 | python sdks/python-cli/examples/goals_to_ics.py - goals.ics

# Export as calendar milestone events (VEVENT) for Google Calendar / Apple Calendar grid
python sdks/python-cli/examples/goals_to_ics.py goals_0.json milestones.ics --format event

# Combine multiple pages with a custom calendar display name
python sdks/python-cli/examples/goals_to_ics.py goals_0.json goals_200.json okrs.ics --calendar-name "My 2026 OKRs" --force
```

### CLI Options

| Argument | Description | Default |
|:---|:---|:---|
| `SOURCE ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `DESTINATION` | Destination path for the `.ics` file | *(required)* |
| `--format` | Component format: `todo` (VTODO), `event` (VEVENT), or `both` (#18594) | `todo` |
| `--calendar-name` | Calendar display name (`X-WR-CALNAME`) | `"Omi Goals"` |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

## 3. Sample output (.ics)

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//omi-cli examples//goals_to_ics//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Omi Goals
BEGIN:VTODO
UID:goal-0192e4a1-b847@omi
DTSTAMP:20260924T120000Z
CREATED:20260901T080000Z
LAST-MODIFIED:20260920T100000Z
SUMMARY:Read 25 technical books
DESCRIPTION:Type: Numeric\nProgress: 60% (15/25 books)\nStatus: Active\nGoal ID: 0192e4a1-b847
STATUS:NEEDS-ACTION
PERCENT-COMPLETE:60
DUE:20261231T235959Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Goal milestone due: Read 25 technical books
TRIGGER:-P1D
END:VALARM
END:VTODO
END:VCALENDAR
```

## 4. Calendar App Integration

- **Apple Calendar / Reminders**: Double-click `goals.ics` to import into the Reminders or Calendar app.
- **Google Calendar**: Open **Settings $\to$ Import & Export $\to$ Import** and select your `.ics` file.
- **Automated Verification**: Run the automated test suite with:
  ```sh
  python sdks/python-cli/tests/test_goals_to_ics.py
  ```
