# Export action items to RFC 5545 VTODO iCalendar task feeds

Use this recipe to convert Omi action items and tasks into standard iCalendar files with `VTODO` components. Unlike standard calendar events (`VEVENT`), `VTODO` components are recognized by **Apple Reminders**, **Things 3**, **OmniFocus**, **2Do**, and CalDAV task servers as native actionable checklist items with completion states (`STATUS:COMPLETED` or `STATUS:NEEDS-ACTION`) and due dates.

It includes RFC 5545 text escaping, completion percent mapping, and status filtering (`--status open`).

## Exporting Action Items

Fetch action items with `omi-cli`:

```bash
omi --json action-item list --limit 200 > action_items.json
```

Or pipe directly into the exporter:

```bash
omi --json action-item list | python action_items_to_vtodo.py - -o ~/Tasks.ics
```

## Running the Exporter

Convert saved action items to a VTODO `.ics` file:

```bash
python action_items_to_vtodo.py action_items.json -o tasks.ics
```

Export open / pending tasks only:

```bash
python action_items_to_vtodo.py action_items.json -o pending.ics --status open
```

Custom calendar list name:

```bash
python action_items_to_vtodo.py action_items.json -o tasks.ics --name "Work Reminders"
```

## Importing into Task Managers

- **Apple Reminders / macOS**: Double click `tasks.ics` or drag and drop into Apple Reminders. The items appear in your Reminders list with their due dates!
- **Things 3 / OmniFocus / Thunderbird**: Select **File -> Import** and select `tasks.ics`.
