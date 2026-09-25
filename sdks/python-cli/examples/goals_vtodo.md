# Track Omi goals in Reminders and CalDAV task managers (VTODO)

Use this recipe to export your Omi goals and milestone targets into RFC 5545 `VTODO` format. Unlike calendar events (`VEVENT`), `VTODO` items import as actionable checkboxes and progress trackers in Apple Reminders, Things 3, OmniFocus, and Nextcloud/CalDAV servers.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export goals and generate an `.ics` task feed:

```sh
omi --json goal list --limit 100 | python goals_to_vtodo.py - -o goals_tasks.ics
```

Or convert a saved goals export:

```sh
python goals_to_vtodo.py goals.json -o goals_tasks.ics
```

Output:
```
Generated VTODO task feed with 12 goal(s) at goals_tasks.ics
```

## How to Import

- **Apple Reminders (macOS/iOS)**: Double-click or drag `goals_tasks.ics` onto Apple Reminders. It imports each goal as a task item with progress and descriptions.
- **CalDAV / Nextcloud Tasks**: Import via web UI or sync client into your tasks calendar.
- **OmniFocus / Things 3**: Drag and drop the `.ics` file into your inbox.

## Features

- **Accurate Progress Tracking**: Computes `PERCENT-COMPLETE` dynamically from `current_value` and `target_value` (clamped 0–100%, with full support for boolean goals).
- **RFC 5545 Status Mapping**: Maps Omi goal statuses (`achieved`, `focused`, `abandoned`) cleanly to standard statuses (`COMPLETED`, `IN-PROCESS`, `CANCELLED`, or `NEEDS-ACTION`).
- **Contextual Descriptions**: Injects goal type, current/target metrics, and unit metadata into the `DESCRIPTION` field.
- **Pure Standard Library**: Zero external dependencies required.
