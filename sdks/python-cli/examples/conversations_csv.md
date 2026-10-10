# Convert a conversation-list export to CSV

Use this recipe to review conversation metadata in a spreadsheet. It reads a
saved JSON export, makes no network requests, and does not export transcripts.
You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_csv.py conversations.json conversations.csv
```

Import the result as UTF-8, comma-delimited text in Excel or another
spreadsheet application. The converter preserves complete IDs, accents, quoted
text and embedded newlines. Missing fields become empty cells; an empty list
produces the column header only. It refuses to overwrite an existing
destination, and a failed write leaves no partial file behind. Treat the
exported file as private conversation data. For exact
unmodified values, retain the source JSON; the CSV adds an apostrophe to common
formula-like values to make their intended text interpretation explicit.
