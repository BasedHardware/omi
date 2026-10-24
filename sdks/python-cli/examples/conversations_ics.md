# Put your conversation history on a calendar (.ics)

Use this recipe to see when Omi conversations happened, next to your meetings.
It reads a saved JSON export, makes no network requests, does not export
transcripts, and writes one iCalendar file that Google Calendar, Apple Calendar,
Outlook and Thunderbird can import. Each conversation with a `started_at`
becomes an event spanning `started_at`–`finished_at` (30 minutes if
`finished_at` is missing). You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup; to retrieve another page, increase `--offset` by
200 and use a different filename.

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_ics.py conversations.json conversations.ics
```

Multiple pages or piped input are also supported:

```sh
omi --json conversation list | python sdks/python-cli/examples/conversations_to_ics.py - conversations.ics
```

Import the file into your calendar (Google Calendar: Settings → Import & export;
Apple Calendar: File → Import; Outlook: File → Open & Export). Times are stored
in UTC, so the calendar shows them in your local time zone. The event UID is
derived from the conversation ID, so re-importing a fresh export updates the same
events instead of duplicating them in calendars that honour UIDs. Conversations
without a start time are skipped and counted. Titles containing commas,
semicolons or line breaks are escaped, long lines are folded per RFC 5545, and
the converter refuses to overwrite an existing file. Treat the exported file as
private conversation data.
