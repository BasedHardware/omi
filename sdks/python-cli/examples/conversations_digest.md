# Build a conversation digest (daily totals, categories, longest sessions)

Use this recipe to see how much Omi recorded and what it was about, without
reading transcripts: it turns one or more `conversation list` exports into a
short Markdown digest with per-day totals, a category breakdown and the longest
conversations. It reads saved JSON exports, makes no network requests, does not
export transcripts, and writes one Markdown file. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

Export the period you want to summarise (200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 --start-date 2026-09-14T00:00:00Z --end-date 2026-09-21T00:00:00Z > week.json
```

Check that the command succeeded before converting the file. If a page is
full, retrieve the next one with `--offset 200` into a second file; the digest
accepts several files and counts each conversation ID once.

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_digest.py --utc-offset +09:00 week_digest.md week.json
```

The digest accepts raw JSON arrays as well as object envelopes (`{"conversations": [...]}` / `{"data": [...]}`).

The digest has three parts: a per-day table (conversations and recorded hours),
a per-category table sorted by count, and the five longest conversations with
their IDs. Days are calendar days in the time zone you pass with
`--utc-offset`; omit it to bucket by UTC. Recorded time is
`finished_at − started_at`; a conversation without a usable start time is
counted in "Skipped", and one without an end time (or an end before the start)
counts as 0 h but still counts as a conversation. Categories and titles come
from the `structured` object the API returns, so no transcript text is read or
written. The script refuses to overwrite an existing digest, so write to a new
name each run. Treat the digest as private data - it is a summary of when you
were recording and what about.
