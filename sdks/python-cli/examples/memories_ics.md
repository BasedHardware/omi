# Put your memories on a calendar (.ics)

Use this recipe to visualize your Omi memories, facts, and learnings on a calendar
timeline. It reads a saved JSON export, makes no network requests, and generates
an RFC 5545 compliant iCalendar (.ics) file that Google Calendar, Apple Calendar,
Microsoft Outlook, and Thunderbird can import. Each memory becomes an event at its
`created_at` timestamp with a 15-minute slot. Memories missing a timestamp are
safely skipped and reported.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export. Pure
standard library only — zero extra dependencies.

## Step 1: Export memories

Export up to 200 memories (the maximum page size supported by `memory list`):

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This represents one page.
To retrieve subsequent pages, increase `--offset` by 200 and save to a new filename:

```sh
omi --json memory list --limit 200 --offset 200 > memories_200.json
```

## Step 2: Convert to iCalendar

Run the converter script [`memories_to_ics.py`](memories_to_ics.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/memories_to_ics.py memories_0.json -o memories.ics
```

To overwrite an existing calendar file:

```sh
python sdks/python-cli/examples/memories_to_ics.py memories_0.json -o memories.ics --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_ics.py - -o memories.ics
```

## Calendar Event Mapping

| iCalendar Field | Source Value / Format | Behavior |
|---|---|---|
| `UID` | `omi-memory-{id}@omi-cli` | Deterministic unique ID for calendar sync deduplication. |
| `DTSTART` / `DTEND` | `created_at` (UTC) | Naive UTC timestamp; default 15-minute event duration. |
| `SUMMARY` | First line of `content` | Escaped per RFC 5545 §3.3.11, capped to 80 characters. |
| `DESCRIPTION` | Full content + metadata | Full memory text with category, tags, visibility, and ID. |
| `CATEGORIES` | `category` | Memory classification (e.g. `work`, `learning`, `personal`). |

## Standards & Reliability Invariants

- **RFC 5545 §3.1 Octet Folding**: Folds content lines at 75 octets without splitting multi-byte UTF-8 character sequences.
- **RFC 5545 §3.3.11 Text Escaping**: Escapes semicolons (`\;`), commas (`\,`), backslashes (`\\`), and newlines (`\n`).
- **CRLF Line Endings**: Emits standard `\r\n` line delimiters required by calendar software.
- **Atomic File Writing**: Writes the calendar to a `.partial` file before atomically renaming via `os.replace`, preventing corrupted files on interrupted runs.
- **Path Traversal Protection**: Rejects paths containing `..` components.
- **Privacy Notice**: Treat the exported calendar file as private data.
