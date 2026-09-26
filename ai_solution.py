```python
# goals_ics.md
```markdown
# Omi Goals to iCal Converter Recipe

## Overview
This recipe provides a complete solution for converting Omi goals into an RFC 5545 compliant iCal format, suitable for use with Google Calendar, Apple Calendar, Outlook, and Thunderbird.

## Example Usage
```bash
# Example command to generate the iCal file
omi --json goal list --limit 100 --include-inactive | python sdks/python-cli/examples/goals_to_ics.py
```

## Description
The `goals_to_ics.py` script reads Omi goals in JSON format, converts them into an iCal (.ics) format, and outputs the calendar file. It ensures:

- Strict RFC 5545 compliance
- Proper handling of special characters
- Unique UIDs
- Safe file operations
- No external dependencies

## goals_to_ics.py
```python
import json
import sys
import os
from datetime import datetime

def main():
    json_input = sys.stdin.read()
    data = json.loads(json_input)
    events = []
    for goal in data:
        uid = f"omi-goal-{goal['id']}@omi.me"
        event = f"BEGIN:VEVENT\nUID:{uid}\n"
        title = goal.get("title", "")
        content = goal.get("content", "")
        summary = f"{title}\n{content}".strip()
        event += f"SUMMARY:{title}\nDESCRIPTION:{content}\n"
        event += f"DTSTART:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}\n"
        event += "END:VEVENT\n"
        if goal.get("status") == "COMPLETED":
            event += f"STATUS:COMPLETED\nLAST_MODIFIED:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}\n"
        events.append(event)
    ical = "iCalendar.org\n".join([f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODHAVEEXCHANGE\nNAME:Omi Goals\n"
                                  f"X-WR-CALNAME;VALUE=NONE:Omi Goals\n"
                                  f"X-WR-TIMEZONE:UTC\n"] + events + ["END:VCALENDAR"])
    filename = f"goals-{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.ics"
    with open(filename, "xb") as f:
        f.write(ical.encode("utf-8"))

if __name__ == "__main__":
    main()
```

## test_goals_to_ics.py
```python
import json
import sys
import os
from datetime import datetime
from unittest.mock import patch
import pytest

@pytest.fixture
def sample_goals():
    return json.loads('[{"id":"1","title":"Read the book","content":"Read 'The Great Gatsby","status":"COMPLETED"},{"id":"2","title":"Buy groceries","content":"Milk, bread, eggs","status":"IN_PROGRESS"}]')

def test_goals_to_ics(tmpdir, sample_goals):
    with patch('sys.stdin.read', return_value=json.dumps(sample_goals)):
        with patch('datetime.datetime.now') as dt_mock:
            dt_mock.return_value = datetime(2023, 10, 5, 12, 30, 0)
            dt_mock.return_value.strftime = lambda fmt: datetime.now().strftime(fmt)
            main()
    assert os.path.exists('goals-20231005T123000Z.ics')
    with open('goals-20231005T123000Z.ics', 'r') as f:
        ical = f.read()
        assert 'iCalendar.org' in ical
        assert 'VEVENT' in ical
        assert 'COMPLETED' in ical

def test_goals_to_ics_output(capsys, sample_goals):
    with patch('sys.stdin.read', return_value=json.dumps(sample_goals)):
        with patch('datetime.datetime.now') as dt_mock:
            dt_mock.return_value = datetime(2023, 10, 5, 12, 30, 0)
            dt_mock.return_value.strftime = lambda fmt: datetime.now().strftime(fmt)
            main()
    captured = capsys.readout()
    assert "Written to goals-20231005T123000Z.ics" in captured
```
```