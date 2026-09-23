# Convert memories to a self-contained HTML report, grouped by category

Use this recipe when you want a quick, shareable, browsable view of everything Omi has captured about you — a single `.html` file with memories grouped by category and tagged inline — instead of scrolling a flat list. It reads a saved JSON export, makes no network requests, has zero external CSS/JS (works fully offline from `file://`), and complements [`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your memories:

```sh
omi --json memory list --limit 200 > memories.json
```

Run the converter:

```sh
python sdks/python-cli/examples/memories_to_html.py memories.json report.html
```

Or set a custom page title:

```sh
python sdks/python-cli/examples/memories_to_html.py memories.json report.html --title "About Me"
```

Open `report.html` in any browser. Memories are grouped under a heading per `category` (alphabetically sorted, `uncategorized` for anything missing one), with each memory's tags shown as small pills underneath its content.

**HTML injection safety:** every memory's content and tags are HTML-escaped before being written into the page, so content containing `<`, `&`, or script-like text is always rendered as plain text, never interpreted as markup — the same defensive posture the CSV/Excel recipes apply against formula injection, adapted to a browser-rendered output. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
