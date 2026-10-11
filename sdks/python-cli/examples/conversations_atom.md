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

Save the following as `conversations_to_atom.py`:

```python
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

FEED_TITLE = "Omi conversations"
FEED_ID = "urn:omi:conversations"
EPOCH = "1970-01-01T00:00:00Z"


def text(value):
    """Render a loosely typed field as one line of XML-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as a string; anything non-null is coerced rather
    than rejected. XML 1.0 has no escape sequence for C0 control characters and
    no encoding for lone surrogates, so those are dropped here - one odd
    character must not make the whole feed unparseable.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    return "".join(ch for ch in collapsed if ch >= " " and not "\ud800" <= ch <= "\udfff")


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rfc3339(moment):
    """Atom timestamps are RFC 3339; the feed keeps every one of them in UTC."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def load(sources):
    conversations = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: expected the JSON array from omi --json conversation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each conversation must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: each conversation needs a string id")
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: conversation structured field must be an object or null")
            conversations[item_id] = item
    return conversations


def entries(conversations):
    """Build one entry per conversation, newest first."""
    rows = []
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        structured = item.get("structured") or {}
        complete = start is not None and end is not None and end >= start
        seconds = int((end - start).total_seconds()) if complete else 0
        details = [f"Duration: {seconds / 60:.0f} min"]
        for label, value in (("Category", text(structured.get("category"))),
                             ("Folder", text(item.get("folder_name"))),
                             ("Source", text(item.get("source"))),
                             ("Language", text(item.get("language")))):
            if value:
                details.append(f"{label}: {value}")
        rows.append({
            "id": item_id,
            "title": text(structured.get("title")) or "(untitled conversation)",
            "category": text(structured.get("category")),
            "published": start,
            # An entry needs an update time: the end of the recording, or its
            # start when the end is missing or earlier than the start.
            "updated": end if complete else start,
            "summary": " - ".join(details),
            "sort": start if start is not None else datetime.min.replace(tzinfo=timezone.utc),
        })
    rows.sort(key=lambda row: (row["sort"], row["id"]), reverse=True)
    return rows


def feed(rows):
    stamps = [rfc3339(row["updated"]) for row in rows if row["updated"] is not None]
    parts = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>",
             "<feed xmlns=\"http://www.w3.org/2005/Atom\">",
             f"<title>{escape(FEED_TITLE)}</title>",
             f"<id>{FEED_ID}</id>",
             # Every stamp is UTC and fixed width, so the newest one sorts last.
             f"<updated>{max(stamps) if stamps else EPOCH}</updated>",
             "<author><name>Omi</name></author>"]
    for row in rows:
        # Percent-encoding keeps the entry id a valid IRI whatever the export
        # holds; an ordinary conversation ID passes through unchanged.
        parts += ["<entry>",
                  f"<title>{escape(row['title'])}</title>",
                  f"<id>urn:omi:conversation:{quote(row['id'], safe='')}</id>",
                  f"<updated>{rfc3339(row['updated']) if row['updated'] is not None else EPOCH}</updated>"]
        if row["published"] is not None:
            parts.append(f"<published>{rfc3339(row['published'])}</published>")
        if row["category"]:
            parts.append(f"<category term={quoteattr(row['category'])}/>")
        parts += [f"<summary type=\"text\">{escape(row['summary'])}</summary>", "</entry>"]
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def convert(sources, destination):
    rows = entries(load(sources))
    # Build and encode the whole feed before touching the filesystem.
    payload = feed(rows).encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing feed; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(rows)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("Usage: python conversations_to_atom.py OUTPUT.xml INPUT.json [INPUT.json ...]")
    try:
        count = convert(args[1:], args[0])
    except (OSError, ValueError) as exc:
        sys.exit(f"Atom export failed: {exc}")
    print(f"{count} entr{'y' if count == 1 else 'ies'} written to {args[0]}")
```

Run it (the output file comes first, then one or more exports):

```sh
python conversations_to_atom.py conversations.xml conversations.json
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
