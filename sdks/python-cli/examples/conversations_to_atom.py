import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

FEED_ID = "urn:omi-cli:conversations"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def parse_dt(value):
    """Parse an exported timestamp to a UTC-aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rfc3339(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def xml_clean(value):
    """Filter out characters that XML 1.0 cannot represent."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # XML 1.0 excludes most control chars and all lone surrogates; drop rather
    # than fail, since one odd title or category must not break the whole feed.
    return "".join(
        ch for ch in value
        if ch in ("\t", "\n", "\r")
        or "\x20" <= ch <= "\ud7ff"
        or "\ue000" <= ch <= "\ufffd"
        or ch >= "\U00010000"
    )


def xml_text(value):
    """Render a field as escaped Atom text, dropping chars XML 1.0 can't hold."""
    return escape(xml_clean(value))


def entry_iri(conversation_id):
    # Percent-encode so ids containing spaces or "/?" still form a valid IRI.
    return f"{FEED_ID}:{quote(str(conversation_id), safe='')}"


def build_entry(item):
    if not isinstance(item, dict):
        raise ValueError("Each conversation must be an object")
    conversation_id = item.get("id")
    if not conversation_id:
        raise ValueError("Conversation is missing an id")

    structured = item.get("structured")
    if structured is None:
        structured = {}
    if not isinstance(structured, dict):
        raise ValueError("Conversation structured field must be an object or null")

    title = structured.get("title") or "Untitled conversation"
    category = structured.get("category")

    started = parse_dt(item.get("started_at"))
    finished = parse_dt(item.get("finished_at"))
    if finished is None or (started is not None and finished < started):
        finished = started

    updated_dt = finished or started
    sort_key = updated_dt or EPOCH
    updated = rfc3339(updated_dt) if updated_dt is not None else rfc3339(EPOCH)
    published = rfc3339(started) if started is not None else None

    if started is not None and finished is not None:
        duration_min = max(0, int((finished - started).total_seconds() // 60))
    else:
        duration_min = 0

    folder = item.get("folder_id") or "-"
    source = item.get("source") or "-"
    language = item.get("language") or structured.get("language") or "-"
    summary = f"Duration: {duration_min} min | Folder: {folder} | Source: {source} | Language: {language}"

    lines = ["  <entry>", f"    <id>{xml_text(entry_iri(conversation_id))}</id>",
             f"    <title>{xml_text(title)}</title>"]
    if category:
        lines.append(f"    <category term={quoteattr(xml_clean(category))} />")
    if published is not None:
        lines.append(f"    <published>{published}</published>")
    lines.append(f"    <updated>{updated}</updated>")
    lines.append(f"    <summary>{xml_text(summary)}</summary>")
    lines.append("  </entry>")
    return "\n".join(lines), sort_key, str(conversation_id)


def convert(sources, destination):
    if isinstance(sources, (str, Path)):
        sources = [sources]
    seen_ids = set()
    entries = []
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError("Expected the JSON array from omi --json conversation list")
        for item in items:
            entry_xml, sort_key, conversation_id = build_entry(item)
            if conversation_id in seen_ids:
                continue
            seen_ids.add(conversation_id)
            entries.append((sort_key, entry_xml))

    # Newest first; ties keep first-seen order (stable sort).
    entries.sort(key=lambda pair: pair[0], reverse=True)
    feed_updated = rfc3339(max((key for key, _ in entries), default=EPOCH))

    body = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <id>{xml_text(FEED_ID)}</id>",
        "  <title>omi conversations</title>",
        f"  <updated>{feed_updated}</updated>",
    ]
    body.extend(entry_xml for _, entry_xml in entries)
    body.append("</feed>")
    # Format everything before touching the filesystem, so a failure can't
    # leave a truncated feed behind.
    payload = ("\n".join(body) + "\n").encode("utf-8")

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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python conversations_to_atom.py INPUT.json [INPUT2.json ...] OUTPUT.xml")
    try:
        convert(sys.argv[1:-1], sys.argv[-1])
    except (OSError, ValueError) as exc:
        sys.exit(f"Atom export failed: {exc}")
