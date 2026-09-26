"""
Convert Omi conversations JSON exports to standard RSS 2.0 feed XML for RSS readers and aggregators.

Usage:
    # Single export
    python conversations_to_rss.py conversations.xml conversations.json

    # Merged multi-page exports (automatically deduplicated by conversation ID)
    python conversations_to_rss.py feed.xml page1.json page2.json page3.json
"""

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
