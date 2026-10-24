# Build a self-contained HTML report of your conversations

Use this recipe to browse or print a period of Omi conversations without the
CLI or a spreadsheet: it turns one or more `conversation list` exports into a
single HTML file with a summary line, one section per day and a table of the
conversations recorded that day (start time, duration, title, category, folder,
source, language, ID). It reads saved JSON exports, makes no network requests,
does not export transcripts, and writes one HTML file with no scripts, external
stylesheets or images. You need Python 3.10+ and an authenticated `omi-cli` for
the initial export.

Export the period you want to report on (200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 --start-date 2026-09-14T00:00:00Z --end-date 2026-09-21T00:00:00Z > week.json
```

Check that the command succeeded before converting the file. If a page is
full, retrieve the next one with `--offset 200` into a second file; the report
accepts several files and lists each conversation ID once.

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_html.py --utc-offset +09:00 week.html week.json
```

Open `week.html` in any browser; it also prints cleanly, one day per heading.
The summary line counts conversations, recorded hours and days; each day
section lists that day's conversations in start order with their duration
(`finished_at − started_at`, `0 min` when the end is missing or earlier than
the start), title, category, folder, source, language and ID. Days and clock
times use the time zone you pass with `--utc-offset`; omit it for UTC. A
conversation without a usable start time is listed in an "Undated" section at
the end. Titles and categories come from the `structured` object the API
returns, so no transcript text is read or written, and every value is
HTML-escaped, so a title containing `<` or `&` is shown literally rather than
interpreted. The script refuses to overwrite an existing report, so use one
file per period. Treat the file as private data.
