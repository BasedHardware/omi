# Convert action items to iCalendar (.ics)

Use this recipe to export action items from Omi into a standard `.ics` file that can be opened in Apple Calendar, Google Calendar, or Outlook as tasks/reminders. It reads a saved JSON export, makes no network requests, and formats standard RFC 5545 `VTODO` calendar entities.

Export action items:

```sh
omi --json action-item list --limit 100 > action_items.json
```

Convert to iCalendar:

```sh
python action_items_to_ics.py action_items.json tasks.ics
```

Double-click `tasks.ics` or import it into your calendar application.
