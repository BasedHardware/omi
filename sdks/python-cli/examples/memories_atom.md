# Publish your memories as an Atom feed

Use this recipe to follow what Omi remembers about you in a feed reader: it
turns one or more `memory list` exports into a single Atom 1.0 file that
NetNewsWire, Thunderbird, Feedly's local import or any other reader can
subscribe to over a `file://` path. Each memory becomes one entry with its
category, tags and creation time, newest first. It reads saved JSON exports,
makes no network requests, and writes one XML file. You need Python 3.10+ and
an authenticated `omi-cli` for the initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account export. To retrieve another page, increase `--offset` by
200 into a second file; the converter accepts several files and includes each
memory ID once. Changes to the account between requests can affect offset
pagination; this recipe does not promise a consistent snapshot.

Save the following as `memories_to_atom.py` (the same script is kept next to
this recipe as [`memories_to_atom.py`](memories_to_atom.py) and covered by
`tests/test_memories_to_atom.py`):

```python
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

FEED_TITLE = "Omi memories"
FEED_ID = "urn:omi:memories"
EPOCH = "1970-01-01T00:00:00Z"


def text(value):
    """Render a loosely typed field as one line of XML-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not break the
    feed, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return clean(value)


def clean(value):
    """Drop characters XML 1.0 cannot carry and escape the rest."""
    out = []
    for ch in value:
        code = ord(ch)
        # Control characters other than tab/newline/carriage-return, plus
        # surrogates and non-characters, are not representable in XML 1.0.
        if code in (0x9, 0xA, 0xD) or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF:
            out.append(ch)
    return escape("".join(out))


def timestamp(value):
    """Normalise an exported datetime to an Atom (RFC 3339, UTC) stamp."""
    if not isinstance(value, str) or not value.strip():
        return EPOCH
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summary(entry):
    """One-line, human-readable metadata for one memory.

    Content itself is not repeated in the summary: a memory can hold private
    text, and the feed only needs to say what kind of memory arrived and when.
    """
    parts = []
    category = text(entry.get("category"))
    if category:
        parts.append(f"category: {category}")
    visibility = text(entry.get("visibility"))
    if visibility:
        parts.append(f"visibility: {visibility}")
    tags = entry.get("tags")
    if isinstance(tags, list) and tags:
        parts.append("tags: " + ", ".join(text(t) for t in tags))
    parts.append(f"created: {timestamp(entry.get('created_at'))}")
    return " | ".join(parts)


def entries_from(documents, seen, entries):
    """Append one Atom entry per memory, skipping duplicate ids."""
    for document in documents:
        if not isinstance(document, list):
            raise ValueError("expected a JSON array of memories")
        for entry in document:
            if not isinstance(entry, dict):
                continue
            memory_id = text(entry.get("id"))
            if not memory_id or memory_id in seen:
                continue
            seen.add(memory_id)
            title = text(entry.get("content")) or "(untitled memory)"
            created = timestamp(entry.get("created_at"))
            entries.append(
                {
                    "id": f"urn:omi:memory:{quote(memory_id, safe='')}",
                    "title": title,
                    "updated": created,
                    "published": created,
                    "category": text(entry.get("category")),
                    "summary": summary(entry),
                }
            )


def render(entries):
    """Serialise entries as Atom 1.0, newest first."""
    ordered = sorted(entries, key=lambda e: e["updated"], reverse=True)
    updated = ordered[0]["updated"] if ordered else EPOCH
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(FEED_TITLE)}</title>",
        f"  <id>{escape(FEED_ID)}</id>",
        f"  <updated>{updated}</updated>",
    ]
    for item in ordered:
        lines.append("  <entry>")
        lines.append(f'    <title type="text">{item["title"]}</title>')
        lines.append(f"    <id>{item['id']}</id>")
        lines.append(f"    <updated>{item['updated']}</updated>")
        lines.append(f"    <published>{item['published']}</published>")
        if item["category"]:
            lines.append(f"    <category term={quoteattr(item['category'])}/>")
        lines.append(f'    <summary type="text">{item["summary"]}</summary>')
        lines.append("  </entry>")
    lines.append("</feed>")
    return "\n".join(lines) + "\n"


def convert(output, inputs):
    """Write one Atom feed from one or more memory exports."""
    out_path = Path(output)
    if out_path.exists():
        raise ValueError(f"refusing to overwrite existing file: {output}")
    entries = []
    seen = set()
    for name in inputs:
        with open(name, encoding="utf-8") as handle:
            entries_from([json.load(handle)], seen, entries)
    result = render(entries)
    out_path.write_text(result, encoding="utf-8")
    return len(entries)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("Usage: python memories_to_atom.py OUTPUT.xml INPUT.json [INPUT.json ...]")
    try:
        count = convert(args[0], args[1:])
    except (OSError, ValueError) as exc:
        sys.exit(f"Atom export failed: {exc}")
    print(f"{count} memor{'y' if count == 1 else 'ies'} written to {args[0]}")
```

Run it (the output file comes first, then one or more exports):

```sh
python memories_to_atom.py memories.xml memories.json
```

Add the resulting file to a reader as a local subscription, or serve the folder
over HTTP if your reader will not open `file://` paths. Entries are ordered
newest first. Each entry carries the memory content as its title, the `category`
as an Atom category term, `published` and `updated` from `created_at`, and a
plain-text summary with the category, visibility, tags and creation time.
Content is not repeated inside the summary, so the metadata line stays short.
Every value is XML-escaped, and control characters, lone surrogates and
non-characters are dropped, so an unusual memory produces a feed that still
parses rather than a broken one. Entry IDs are percent-encoded. Re-running with
more export files regenerates the feed with each memory listed once; the script
refuses to overwrite an existing file, so delete the old feed first or write to
a new name. Treat the feed as private data - it is a list of the facts Omi has
saved about you, and the entry titles are those facts.
