```python
import datetime
import json
from pathlib import Path
from urllib.parse import urljoin

def atom_date(value):
    if value is None:
        return None
    date_obj = datetime.datetime.fromisoformat(value)
    return date_obj.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def xml_escape(text):
    from xml.sax.saxutils import escape
    return escape(text)

def main():
    memories = json.loads(Path("memories.json").read_text())
    feed_title = "Memories"
    feed_url = "https://example.com/memories"
    entries = []
    for memory in sorted(memories, key=lambda x: x.get('created_at'), reverse=True):
        entry = {
            "title": str(memory.get("id")),
            "link": urljoin(feed_url, str(memory.get("id"))),
            "id": str(memory.get("id")),
            "summary": (
                f"Category: {memory.get('category')}; "
                f"Visibility: {memory.get('visibility')}; "
                f"Tags: {', '.join(memory.get('tags', []))}; "
                f"Created: {atom_date(memory.get('created_at'))}"
            ),
            "published": atom_date(memory.get('created_at')),
            "updated": atom_date(memory.get('created_at')),
            "categories": memory.get('tags', []),
        }
        entries.append(entry)
    feed = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://purl.org/atom/1.0">
    <title>{xml_escape(feed_title)}</title>
    <link href="{feed_url}"/>
    <updated>{datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")}</updated>
    <icon>{feed_url}</icon>
    <entry>
        <id>{xml_escape(feed_url)}</id>
        <title>{xml_escape(feed_title)}</title>
        <link href="{feed_url}"/>
        <updated>{datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")}</updated>
        <category term="omnivox" scheme="https://omnivox.ai/"/>
    </entry>
</feed>
"""
    for entry in entries:
        feed += f"""<entry>
            <id>{entry["id"]}</id>
            <title>{xml_escape(entry["title"])}</title>
            <link href="{entry["link"]}" />
            <summary>{xml_escape(entry["summary"])}</summary>
            <published>{entry["published"]}</published>
            <updated>{entry["updated"]}</updated>
            <category term="; ".join(entry["categories"]) scheme="https://omnivox.ai/"/>
        </entry>"""
    feed = feed.replace("    ", "\t")  # Adjust for XML formatting
    print(feed)

if __name__ == "__main__":
    main()
```