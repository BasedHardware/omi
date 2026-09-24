# Build a self-contained HTML report of your action items

Convert Omi action items JSON exports to a clean, self-contained, printable HTML report with task status cards, open and completed task tables, and zero external dependencies.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

### Export directly via CLI pipeline

```sh
omi --json action-item list | python action_items_to_html.py - -o tasks.html
```

### Export from a saved JSON file

```sh
python action_items_to_html.py action_items.json -o tasks.html
```

### Merging multiple export pages

```sh
python action_items_to_html.py page1.json page2.json -o all_tasks.html
```

## Running the Bundled Script

You can run the bundled recipe directly:

```sh
python sdks/python-cli/examples/action_items_to_html.py action_items.json -o tasks.html
```

## Features

- **Dashboard Metric Cards**: Instant high-level count of Total Tasks, Open Tasks, Completed Tasks, and overall Completion Rate.
- **Sectioned Layout**: Distinct tables for `📋 Open Tasks` and `✅ Completed Tasks` with color-coded status badges.
- **Print & PDF Ready**: Embedded CSS includes `@media print` rules for clean paper printing or PDF export.
- **Safe & Self-Contained**: 100% standard library with strict HTML escaping against XSS; zero external fonts, scripts, or stylesheets.
