# Build a self-contained HTML report of your action items

Use this recipe to browse, audit, or print your Omi tasks and action items without the
CLI or a spreadsheet: it turns one or more `action-item list` exports into a
single, self-contained HTML file with status summaries (Pending Tasks vs Completed Tasks),
due dates, creation timestamps, and links back to originating conversations.

It reads saved JSON exports, makes zero network requests, and writes a single HTML file with
no external scripts, stylesheets, or images (100% offline and print-friendly). You need Python 3.10+
and an authenticated `omi-cli` for the initial export.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Export your action items (up to 200 items per page):

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

If you have more items, export subsequent pages with `--offset 200` into separate files:

```sh
omi --json action-item list --limit 200 --offset 200 > action_items_200.json
```

---

## Generating the HTML Report

Run `action_items_to_html.py` with the output destination and one or more input JSON exports:

```sh
python action_items_to_html.py --utc-offset +07:00 tasks_report.html action_items_0.json action_items_200.json
```

### Options

- `--utc-offset <+HH:MM | -HH:MM>`: Adjusts timestamps from UTC to your local time zone (e.g. `+07:00` for Hanoi/Bangkok, `-05:00` for US Eastern). Omit for UTC.
- The output file is created with exclusive write (`xb`) guards to prevent accidental overwriting of existing reports.

---

## Features

- **Offline & Self-Contained:** Zero dependencies outside the Python standard library. No external CDN fonts, CSS frameworks, or JavaScript trackers.
- **Status Sections:** Separates tasks into **📌 Pending Tasks** and **✅ Completed Tasks** with color-coded badges and task counts.
- **Timezone-Aware:** Converts ISO-8601 UTC timestamps to local dates and times.
- **Security & XSS Protection:** All task descriptions, IDs, and conversation keys are safely HTML-escaped.
- **Print Optimization:** Formatted with print-friendly CSS page breaks for clean PDF export or physical printing.
