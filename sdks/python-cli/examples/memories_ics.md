# Memories to iCalendar (.ics) Export Recipe

Export Omi memories to RFC 5545-compliant iCalendar files for calendar applications.

## Prerequisites
- Python 3.8+
- Omi CLI installed (`pip install omi-cli`)

## Export Command
```bash
# Export memories to ICS file (UTC events, 15-minute slots)
omi memories export --output memories.ics
```

## RFC 5545 Compliance
| Requirement               | Implementation                          |
|---------------------------|----------------------------------------|
| §3.1 Line Folding          | 75-octet lines, UTF-8 safe              |
| §3.3.11 Text Escaping      | Backslash escaping for special chars  |
| Event Duration            | 15-minute slots from `created_at`      |
| File Writing              | Exclusive mode (`xb`) to prevent corruption

## Validation
```bash
# Check ICS file validity
icalendar --check memories.ics
```

## Import Targets
- Google Calendar: File → Import
- Apple Calendar: File → Import
- Outlook: Open → Import/Export

## Notes
- Events use UTC timezone (RFC 5545 `TZID:UTC`)
- Memory descriptions are escaped per §3.3.11
- File is written atomically to prevent partial writes

## Example Output (Truncated)
```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Omi//EN
BEGIN:VEVENT
UID:mem-12345
DTSTAMP:20230101T120000Z
DTSTART:20230101T120000Z
DTEND:20230101T121500Z
SUMMARY:Memory Title
DESCRIPTION:Escaped\; text content\

END:VEVENT
END:VCALENDAR
```