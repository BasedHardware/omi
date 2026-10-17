# Publish your conversations as an Atom feed

Use this recipe to follow your own Omi recordings in a feed reader: it turns one
or more `conversation list` exports into a single Atom 1.0 file that NetNewsWire,
Thunderbird, Feedly's local import or any other reader can subscribe to over a
`file://` path. Each conversation becomes one entry with its title, category,
timestamps and a one-line metadata summary, newest first. It reads saved JSON
exports, makes no network requests, does not export transcripts, and writes one
XML file. You need Python 3.10+ and an authenticated `omi-cli` for the initial
export.

Export the conversations you want in the feed (200 per page):

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. If a page is full,
retrieve the next one with `--offset 200` into a second file; the converter
accepts several files and includes each conversation ID once.

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_atom.py conversations.xml conversations.json
```

Multiple export pages can be merged in a single feed:

```sh
python sdks/python-cli/examples/conversations_to_atom.py conversations.xml page1.json page2.json
```

Add the resulting file to a reader as a local subscription, or serve the folder
over HTTP if your reader will not open `file://` paths. Entries are ordered
newest first; each one carries the conversation title, the `category` as an
Atom category term, `published` (`started_at`), `updated` (`finished_at`, or the
start when the end is missing or earlier than the start) and a plain-text
summary with the duration, folder, source and language. Titles and categories
come from the `structured` object the API returns, so no transcript text is read
or written. Every value is XML-escaped, control characters and lone surrogates
are dropped, and entry IDs are percent-encoded, so an unusual title or ID
produces a feed that still parses rather than a broken one. Re-running with more
export files regenerates the feed with each conversation listed once; the script
refuses to overwrite an existing file, so delete the old feed first or write to
a new name. Treat the feed as private data - it is a list of when you were
recording and what about.
