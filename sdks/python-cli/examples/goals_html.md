# Convert a goal-list export to a self-contained HTML progress report

Use this recipe when you want a quick, shareable, at-a-glance view of your tracked goals — a single `.html` file with a progress bar per goal, grouped into Active and Completed/Inactive — instead of scanning rows in a spreadsheet. It reads a saved JSON export, makes no network requests, and has zero external CSS/JS (nothing to fetch, works fully offline from `file://`).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export tracked goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Run the converter:

```sh
python sdks/python-cli/examples/goals_to_html.py goals.json report.html
```

Or set a custom page title:

```sh
python sdks/python-cli/examples/goals_to_html.py goals.json report.html --title "Q3 Goals"
```

Open `report.html` in any browser. Each goal shows a progress bar (`current_value / target_value`), falling back to the `min_value`–`max_value` range when `target_value` isn't usable (e.g. `0`, for boolean/scale goals). Goals are split into an **Active** section and a **Completed / Inactive** section.

**HTML injection safety:** every goal field (title, unit) is HTML-escaped before being written into the page, so a title or unit containing `<`, `&`, or script-like text is always rendered as plain text, never interpreted as markup — the same defensive posture the CSV/Excel recipes apply against formula injection, adapted to a browser-rendered output. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
