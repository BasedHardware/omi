# Publish your conversations as an RSS 2.0 feed

Use this recipe to follow your own Omi recordings in standard RSS feed readers,
podcast players, and team aggregators: it turns one or more `conversation list`
exports into a single RSS 2.0 XML file that Feedly, NetNewsWire, Thunderbird,
Slack RSS bots, or any reader can subscribe to over a `file://` path or local server.
Each conversation becomes one item with its title, category, RFC 822 timestamps,
and a clean metadata summary, newest first. It reads saved JSON exports, makes no
network requests, does not export transcripts, and writes one XML file. You need
Python 3.10+ and an authenticated `omi-cli` for the initial export.

### Privacy Notice

> [!NOTE]
> Treat the generated RSS feed as sensitive personal data. While it does not include
> raw audio or full transcript text, conversation titles, category tags, folders,
> and timestamps reveal when and where you were active and what topics you discussed.

## Quickstart

Export the conversations you want in the feed (up to 200 per page):

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. If a page is full,
retrieve the next one with `--offset 200` into a second file; the converter
accepts multiple files and deduplicates each conversation ID automatically:

```sh
python examples/conversations_to_rss.py conversations.xml conversations.json
# Or with multiple pages:
python examples/conversations_to_rss.py feed.xml page1.json page2.json page3.json
```

## Standalone Converter Script

The standalone exporter is located at `examples/conversations_to_rss.py`:

```python
import json
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

FEED_TITLE = "Omi conversations"
FEED_LINK = "https://www.omi.me"
FEED_DESCRIPTION = "Exported conversations from Omi"


def text(value):
    """Render a loosely typed field as one line of XML-safe text."""
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


def rfc822(moment):
    """Format an aware UTC datetime as RFC 822 / RFC 2822 for RSS 2.0 pubDate."""
    if moment is None:
        return None
    return format_datetime(moment, usegmt=True)


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
            "updated": end if complete else start,
            "summary": " - ".join(details),
            "sort": start if start is not None else datetime.min.replace(tzinfo=timezone.utc),
        })
    rows.sort(key=lambda row: (row["sort"], row["id"]), reverse=True)
    return rows


def feed(rows):
    latest_moment = max([row["updated"] for row in rows if row["updated"] is not None], default=None)
    last_build = rfc822(latest_moment) if latest_moment else rfc822(datetime.now(timezone.utc))
    parts = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>",
             "<rss version=\"2.0\">",
             "<channel>",
             f"<title>{escape(FEED_TITLE)}</title>",
             f"<link>{escape(FEED_LINK)}</link>",
             f"<description>{escape(FEED_DESCRIPTION)}</description>",
             f"<lastBuildDate>{last_build}</lastBuildDate>",
             "<generator>Omi CLI RSS Exporter</generator>"]
    for row in rows:
        parts += ["<item>",
                  f"<title>{escape(row['title'])}</title>",
                  f"<guid isPermaLink=\"false\">urn:omi:conversation:{quote(row['id'], safe='')}</guid>"]
        if row["published"] is not None:
            parts.append(f"<pubDate>{rfc822(row['published'])}</pubDate>")
        if row["category"]:
            parts.append(f"<category>{escape(row['category'])}</category>")
        parts += [f"<description>{escape(row['summary'])}</description>", "</item>"]
    parts += ["</channel>", "</rss>"]
    return "\n".join(parts) + "\n"


def convert(sources, destination):
    rows = entries(load(sources))
    payload = feed(rows).encode("utf-8")
    output_path = Path(destination)
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
        sys.exit("Usage: python conversations_to_rss.py OUTPUT.xml INPUT.json [INPUT.json ...]")
    try:
        count = convert(args[1:], args[0])
    except (OSError, ValueError) as exc:
        sys.exit(f"RSS export failed: {exc}")
    print(f"{count} item{'s' if count != 1 else ''} written to {args[0]}")
```

Add the resulting file to your RSS reader or podcast tool as a local subscription,
or serve the directory over HTTP if your reader requires remote URLs. Entries are
ordered newest first; each item carries the conversation title, `pubDate` formatted
according to RFC 822 / RFC 2822, `category` metadata, a stable non-permalink GUID,
and a plain-text summary containing duration, folder, source, and language. Titles
and categories come from the `structured` object returned by the API, so no private
transcript text is parsed or leaked. Every field is XML-escaped and control characters
are pruned to guarantee standard parser compatibility.
