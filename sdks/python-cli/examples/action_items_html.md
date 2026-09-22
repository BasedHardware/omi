# Convert action items to a self-contained HTML checklist report

Use this recipe when you want a quick, shareable, at-a-glance view of your action items — a single `.html` file with a checklist grouped into Open and Completed, overdue items flagged — instead of scanning a CSV or a terminal table. It reads a saved JSON export, makes no network requests, has zero external CSS/JS (works fully offline from `file://`), and complements [`action_items_markdown.md`](action_items_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your action items:

```sh
omi --json action-item list --limit 200 > action_items.json
```

Run the converter:

```sh
python sdks/python-cli/examples/action_items_to_html.py action_items.json report.html
```

Or set a custom page title:

```sh
python sdks/python-cli/examples/action_items_to_html.py action_items.json report.html --title "This Week"
```

Open `report.html` in any browser. Each item shows a checkbox (☐/☑), its description, and a due date if any — **overdue open items** (a due date in the past, not yet completed) are highlighted in red. Items are split into an **Open** section and a **Completed** section.

**HTML injection safety:** every item's description is HTML-escaped before being written into the page, so a description containing `<`, `&`, or script-like text is always rendered as plain text, never interpreted as markup — the same defensive posture the CSV/Excel recipes apply against formula injection, adapted to a browser-rendered output. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
