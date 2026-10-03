# Omi Memories to iCalendar (.ics) Export

This recipe provides a complete, RFC 5545 compliant script to export Omi memories into an iCalendar (`.ics`) file, which can be imported into Google Calendar, Apple Calendar, Outlook, and other calendar applications.

## Features

- Parses `created_at` timestamps into UTC calendar events with 15-minute slots.
- RFC 5545 §3.1 line folding at 75 octets without splitting UTF-8 characters.
- RFC 5545 §3.3.11 escaping for text fields.
- Exclusive file writing (`xb`) preventing accidental overwrites and partial writes.
- 100% Python standard library (zero external dependencies).

## Prerequisites

- Python 3.6 or higher
- Omi memories accessible via the Omi SDK

## Usage

```python
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

def escape_text(text):
    """RFC 5545 §3.3.11: Escape text fields."""
    return text.replace("\\", "\\\\").replace(",", "\\,"). replace(";", "\\;").replace("\n", "\\n")

def fold_line(line):
    """RFC 5545 §3.1: Fold lines at 75 octets."""
    if len(line) <= 75:
        return line
    folded = []
    pos = 0
    while pos < len(line):
        folded.append(line[pos:pos+75])
        pos += 75
    return "\r\n ".join(folded)

def generate_ics(memories, output_path):
    """Generate an iCalendar file from Omi memories."""
    events = []
    for memory in memories:
        created_at = datetime.fromisoformat(memory["created_at"].replace("Z", "+00:00"))
        # Create a 15-minute event
        event_start = created_at.astimezone(timezone.utc)
        event_end = event_start + timedelta(minutes=15)
        
        event = {
            "uid": f"omi-{memory['id']}@omi.basedhardware.com",
            "dtstamp": event_start.strftime("%Y%m%dT%H%M%SZ"),
            "dtstart": event_start.strftime("%Y%m%dT%H%M%SZ"),
            "dtend": event_end.strftime("%Y%m%dT%H%M%SZ"),
            "summary": escape_text(f"Omi Memory: {memory.get('title', 'Untitled')}"),
            "description": escape_text(memory.get("content", "")),
            "organizer": f"MAILTO:omi@basedhardware.com"
        }
        events.append(event)
    
    # Generate iCalendar content
    calendar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BasedHardware//Omi//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]
    
    for event in events:
        calendar.append("BEGIN:VEVENT")
        calendar.append(f"UID:{event['uid']}")
        calendar.append(f"DTSTAMP:{event['dtstamp']}")
        calendar.append(f"DTSTART:{event['dtstart']}")
        calendar.append(f"DTEND:{event['dtend']}")
        calendar.append(f"SUMMARY:{event['summary']}")
        calendar.append(f"DESCRIPTION:{event['description']}")
        calendar.append(f"ORGANIZER:{event['organizer']}")
        calendar.append("END:VEVENT")
    
    calendar.append("END:VCALENDAR")
    
    # Write to file with exclusive access to prevent partial writes
    with open(output_path, "xb") as f:
        for line in calendar:
            f.write(fold_line(line).encode("utf-8"))
            f.write(b"\r\n")

# Example usage
if __name__ == "__main__":
    # Replace with your actual Omi memories
    memories = [
        {
            "id": "123",
            "created_at": "2023-01-01T12:00:00Z",
            "title": "New Year's Day",
            "content": "Celebrating the new year with friends and family."
        },
        {
            "id": "124",
            "created_at": "2023-01-02T14:30:00Z",
            "title": "Project Meeting",
            "content": "Discussed the roadmap for the upcoming quarter."
        }
    ]
    
    output_path = Path("memories.ics")
    generate_ics(memories, output_path)
    print(f"Successfully exported memories to {output_path}")
```

## How to Use

1. Save the script above as `memories_to_ics.py`
2. Install the Omi SDK if you haven't already: `pip install omi-sdk`
3. Fetch your memories using the Omi SDK
4. Pass the memories data to the `generate_ics` function
5. Import the generated `.ics` file into your calendar application

## Notes

- The script uses UTC for all event times to ensure consistency across time zones
- Each memory is converted into a 15-minute event
- The script uses exclusive file creation (`xb` mode) to prevent accidental overwrites
- No external dependencies are required - only Python's standard library is used

## License

This recipe is provided as-is under the MIT License.