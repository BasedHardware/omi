#!/usr/bin/env python3
"""
Convert Omi conversation-list JSON export to a standard Podcast RSS 2.0 XML feed.

Usage:
    python conversations_to_podcast.py conversations.json [conversations2.json ...] -o podcast.xml

Options:
    -o, --output FILE         Output path for the RSS feed (default: podcast.xml)
    --title TITLE             Podcast show title (default: "Omi Conversations")
    --description DESC        Podcast show description (default: "Audio life-log and conversation transcripts from Omi")
    --author AUTHOR           Podcast author / owner (default: "Omi User")
    --audio-base-url URL      Base URL prefix for audio attachments (e.g. "https://storage.googleapis.com/my-recordings/")
    --filter-category CAT     Only include conversations matching this category
    --force                   Overwrite output file if it already exists

Outputs an RSS 2.0 feed with iTunes podcast extensions, fully compatible with
Apple Podcasts, Spotify, Pocket Casts, and any standard podcast reader.
Zero external dependencies (pure Python standard library).
"""

import argparse
import email.utils
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import xml.etree.ElementTree as ET


def parse_rfc822_date(date_str: Optional[str]) -> str:
    """Parse an ISO-8601 timestamp string and format it as RFC 822 / 2822 for RSS pubDate."""
    if not date_str:
        return email.utils.format_datetime(datetime.now(timezone.utc))
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return email.utils.format_datetime(dt)
    except (ValueError, AttributeError):
        return email.utils.format_datetime(datetime.now(timezone.utc))


def format_duration(seconds: Optional[float]) -> Optional[str]:
    """Format duration in seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return None
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def calculate_duration(item: Dict[str, Any]) -> Optional[str]:
    """Calculate duration from explicit fields or start/end timestamps."""
    if "duration" in item and isinstance(item["duration"], (int, float)):
        return format_duration(item["duration"])
    if "duration_seconds" in item and isinstance(item["duration_seconds"], (int, float)):
        return format_duration(item["duration_seconds"])

    # Try started_at and finished_at
    start_str = item.get("started_at")
    end_str = item.get("finished_at") or item.get("ended_at")
    if start_str and end_str:
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            diff = (end_dt - start_dt).total_seconds()
            if diff >= 0:
                return format_duration(diff)
        except (ValueError, AttributeError):
            pass
    return None


def extract_conversations(pages: Sequence[str], category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse one or more JSON export files, deduplicate by ID, and apply filters."""
    seen_ids = set()
    conversations = []

    for path in pages:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
        raw = p.read_text(encoding="utf-8").lstrip("\ufeff")
        items = json.loads(raw)

        # Support raw list or wrapped {"conversations": [...]}, {"items": [...]}
        if isinstance(items, dict):
            for key in ("conversations", "items", "data"):
                if isinstance(items.get(key), list):
                    items = items[key]
                    break

        if not isinstance(items, list):
            raise ValueError(f"{path}: expected a JSON array or object containing a conversations list")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: each conversation must be a JSON dictionary")
            conv_id = item.get("id")
            if not conv_id:
                raise ValueError(f"{path}: conversation missing required 'id' field")

            if conv_id in seen_ids:
                continue
            seen_ids.add(conv_id)

            if category_filter:
                item_cat = str(item.get("category", "")).lower()
                if item_cat != category_filter.lower():
                    continue

            conversations.append(item)

    return conversations


def build_podcast_feed(
    conversations: List[Dict[str, Any]],
    title: str = "Omi Conversations",
    description: str = "Audio life-log and conversation transcripts from Omi",
    author: str = "Omi User",
    audio_base_url: Optional[str] = None
) -> str:
    """Generate an RSS 2.0 XML string with iTunes podcast tags."""
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/"
    })
    channel = ET.SubElement(rss, "channel")

    # Feed metadata
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "link").text = "https://github.com/BasedHardware/omi"
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(datetime.now(timezone.utc))

    # iTunes tags
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = author
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary").text = description
    itunes_owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
    ET.SubElement(itunes_owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}name").text = author
    ET.SubElement(itunes_owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = "support@omi.me"
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "false"
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category", {"text": "Technology"})

    # Sort conversations newest first based on started_at / created_at
    def sort_key(item: Dict[str, Any]) -> str:
        return item.get("started_at") or item.get("created_at") or ""

    sorted_convs = sorted(conversations, key=sort_key, reverse=True)

    for item in sorted_convs:
        entry = ET.SubElement(channel, "item")
        conv_id = item["id"]

        # Item title
        structured = item.get("structured") or {}
        item_title = item.get("title") or structured.get("title")
        if not item_title:
            started = item.get("started_at") or item.get("created_at") or "Unknown Date"
            item_title = f"Conversation {started[:16].replace('T', ' ')}"
        ET.SubElement(entry, "title").text = str(item_title)

        # Item GUID
        guid = ET.SubElement(entry, "guid", {"isPermaLink": "false"})
        guid.text = f"omi:conversation:{conv_id}"

        # Publication date
        date_src = item.get("started_at") or item.get("created_at")
        ET.SubElement(entry, "pubDate").text = parse_rfc822_date(date_src)

        # Description / Content
        desc_parts = []
        if structured.get("overview"):
            desc_parts.append(f"Overview: {structured['overview']}")
        elif item.get("summary"):
            desc_parts.append(f"Summary: {item['summary']}")

        if item.get("category"):
            desc_parts.append(f"Category: {item['category']}")

        if item.get("transcript"):
            desc_parts.append(f"\nTranscript:\n{item['transcript']}")

        full_desc = "\n\n".join(desc_parts) if desc_parts else "No transcript available."
        ET.SubElement(entry, "description").text = full_desc

        # Duration
        dur = calculate_duration(item)
        if dur:
            ET.SubElement(entry, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text = dur

        # Audio enclosure
        audio_url = item.get("audio_url") or item.get("recording_url")
        if not audio_url and audio_base_url:
            base = audio_base_url.rstrip("/")
            audio_url = f"{base}/{conv_id}.mp4"
        elif not audio_url:
            audio_url = f"https://recordings.omi.me/audio/{conv_id}.mp4"

        ET.SubElement(entry, "enclosure", {
            "url": audio_url,
            "type": "audio/mp4",
            "length": str(item.get("audio_size_bytes") or 1048576)
        })

    # Indent XML for readability
    ET.indent(rss, space="  ", level=0)
    xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    return xml_header + ET.tostring(rss, encoding="utf-8").decode("utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation export JSON to a podcast RSS 2.0 XML feed."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON files exported from Omi CLI")
    parser.add_argument("-o", "--output", default="podcast.xml", help="Output RSS XML file path")
    parser.add_argument("--title", default="Omi Conversations", help="Podcast title")
    parser.add_argument("--description", default="Audio life-log and conversation transcripts from Omi", help="Podcast description")
    parser.add_argument("--author", default="Omi User", help="Podcast author name")
    parser.add_argument("--audio-base-url", default=None, help="Base URL prefix for hosted audio files")
    parser.add_argument("--filter-category", default=None, help="Filter conversations by category")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file")

    args = parser.parse_args(argv)

    out_path = Path(args.output)
    if ".." in out_path.parts:
        sys.stderr.write("Error: Path traversal ('..') is not allowed in output path.\n")
        return 2

    if out_path.exists() and not args.force:
        sys.stderr.write(f"Error: Output file already exists: {out_path}. Use --force to overwrite.\n")
        return 1

    try:
        conversations = extract_conversations(args.inputs, category_filter=args.filter_category)
    except Exception as e:
        sys.stderr.write(f"Error reading inputs: {e}\n")
        return 1

    xml_content = build_podcast_feed(
        conversations,
        title=args.title,
        description=args.description,
        author=args.author,
        audio_base_url=args.audio_base_url
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml_content, encoding="utf-8")
    print(f"Exported {len(conversations)} conversations to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
