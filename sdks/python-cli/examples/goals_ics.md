# Put your goals and target deadlines on a calendar (.ics)

Convert Omi goals JSON exports into an iCalendar (`.ics`) file to schedule milestone targets, habit checkpoints, and goal deadlines directly in Apple Calendar, Google Calendar, and Outlook.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

### Export directly via CLI pipeline

```sh
omi --json goal list | python goals_to_ics.py - -o goals.ics
```

### Export from a saved JSON file

```sh
python goals_to_ics.py goals.json -o goals.ics
```

### Merging multiple export pages

```sh
python goals_to_ics.py page1.json page2.json -o all_goals.ics
```

## Running the Bundled Script

You can run the bundled recipe directly:

```sh
python sdks/python-cli/examples/goals_to_ics.py goals.json -o goals.ics
```

## Features

- **Milestone Scheduling**: Maps target dates to 1-hour calendar blocks on your preferred calendar application.
- **Progress Tracking**: Includes current vs target metrics and completion status (`NEEDS-ACTION` or `COMPLETED`) in event descriptions.
- **RFC 5545 Compliant**: Valid iCalendar syntax with 75-octet line folding, strict CRLF formatting, and character escaping.
- **Self-Contained**: 100% Python standard library without external dependencies.
