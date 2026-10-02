```python
#!/usr/bin/env python
"""Convert action items to an Atom feed."""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Convert action items to an Atom feed.')
    parser.add_argument('--status', choices=['open', 'completed', 'all'], default='all',
                       help='Filter by status: open, completed, or all.')
    parser.add_argument('--title', default='Omi Action Items',
                       help='Title for the Atom feed.')
    args = parser.parse_args()

    input = sys.stdin.read().splitlines() if sys.stdin.isatty() else sys.stdin.read()
    items = json.loads(input.strip()) if input.strip() else []

    root = ET.Element('feed', {'xmlns': 'http://www.w3.org/2005/Atom'})
    root.append(ET.Element('title', {'type': 'text'})).text = args.title
    root.append(ET.Element('subtitle', {'type': 'text'})).text = 'Omi Action Items Feed'
    root.append(ET.Element('link', {'href': 'file://{}'.format(Path(__file__).resolve())}))
    root.append(ET.Element('id', {'type': 'uri'})).text = 'file://{}'.format(Path(__file__).resolve())
    root.append(ET.Element('updated', {'type': 'datetime'})).text = datetime.now().isoformat() + 'Z'

    for item in items:
        if args.status == 'open' and item['status'] == 'completed':
            continue
        if args.status == 'completed' and item['status'] != 'completed':
            continue

        entry = ET.SubElement(root, 'entry')
        title = f"[{item['status'].upper()}] {item['text']}"
        if 'due' in item:
            title += f" (due: {item['due']})"
        ET.SubElement(entry, 'title', {'type': 'text'}).text = title

        summary = item['text']
        if 'due' in item:
            summary += f" (due: {item['due']})"
        ET.SubElement(entry, 'summary', {'type': 'text'}).text = summary

        content = f"<p><p><ul><li><strong>{title}</strong></p></li></ul></p>"
        ET.SubElement(entry, 'content', {'type': 'html'}).text = content

        item_id = str(item['id'])
        ET.SubElement(entry, 'id', {'type': 'uri'}).text = f'itemid:{item_id}'

        updated = datetime.fromisoformat(item['updated']).isoformat() + 'Z'
        ET.SubElement(entry, 'updated', {'type': 'datetime'}).text = updated

        categories = [item['status']]
        if 'category' in item:
            categories.append(item['category'])
        ET.SubElement(entry, 'category', {'scheme': 'http://www.omasdk.org/ns/atom#status'}).text = '|'.join(categories)

    ET.indent(root, level=0)
    xml = ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')
    print(xml)

if __name__ == '__main__':
    main()
```