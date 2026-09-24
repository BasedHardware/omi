# Build a self-contained HTML report of your action items

Use this recipe to browse, review, or print your Omi action items and tasks
without requiring third-party tools or external services. It converts one or
more `action-item list` JSON exports into a single, beautiful HTML dashboard
with summary metrics cards (total tasks, pending count, completed count, completion rate)
and structured tables separated by status.

It makes no network requests, contains no tracking scripts, requires no external
stylesheets or CDNs, and includes built-in dark mode support (`prefers-color-scheme: dark`)
and clean `@media print` styles for PDF exporting. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

## Quickstart

### 1. Export Action Items

Export up to 200 action items to a JSON file:

```sh
omi --json action-item list --limit 200 --offset 0 > tasks.json
```

To retrieve older tasks, increase `--offset` by 200 into a second file:

```sh
omi --json action-item list --limit 200 --offset 200 > tasks_page2.json
```

### 2. Generate the HTML Report

Run `action_items_to_html.py` on your exported JSON file(s):

```sh
python action_items_to_html.py tasks.json -o tasks.html
```

Or combine multiple pages into a single report:

```sh
python action_items_to_html.py tasks.json tasks_page2.json -o full_report.html
```

### 3. Direct Pipeline via Stdin

You can pipe data directly from the CLI without saving intermediate JSON files:

```sh
omi --json action-item list --limit 200 | python action_items_to_html.py - -o tasks.html
```

Open the resulting `tasks.html` in any web browser or print it (`Cmd+P` / `Ctrl+P`)
to save as a clean PDF document.

---

## Features

- **Summary Cards:** Quick visual overview of total tasks, pending items, completed items, and completion percentage.
- **Status Separation:** Divides pending and completed tasks into clear tables.
- **Due Date & Timestamp Normalization:** Formats UTC timestamps for human readability.
- **Safe HTML Escaping:** All user-controlled fields (`description`, `id`, `conversation_id`) are safely escaped via `html.escape` to prevent XSS.
- **Self-Contained Styling:** Responsive CSS embedded directly inside `<style>`, ensuring the document renders reliably offline or in email attachments.
