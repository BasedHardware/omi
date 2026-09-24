# Build a self-contained HTML dashboard of your goals

Convert Omi goals JSON exports into an interactive, visual HTML progress dashboard with CSS completion bars, status badges, metric counters, and print-ready styles with zero external dependencies.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

### Export directly via CLI pipeline

```sh
omi --json goal list | python goals_to_html.py - -o goals.html
```

### Export from a saved JSON file

```sh
python goals_to_html.py goals.json -o goals.html
```

### Merging multiple export pages

```sh
python goals_to_html.py page1.json page2.json -o all_goals.html
```

## Running the Bundled Script

You can run the bundled recipe directly:

```sh
python sdks/python-cli/examples/goals_to_html.py goals.json -o goals.html
```

## Features

- **Dashboard Metric Cards**: Live counts of Total Goals, Active Objectives, Completed Goals, Inactive Goals, and overall Completion Rate.
- **Dynamic CSS Progress Bars**: Visual completion bars rendered with standard CSS flex/percentage widths without JavaScript.
- **Categorized Sections**: Groups goals into `🟢 Active Goals`, `🏁 Completed Goals`, and `⚪ Inactive / Archived`.
- **Target Tracking**: Formats current vs target values with custom measurement units (e.g. `15 / 20 books`, `42.2 / 42.2 km`).
- **Print & PDF Support**: Built-in `@media print` rules ensure clean rendering for paper printing, PDF generation, or e-ink displays.
- **Safe & Self-Contained**: 100% Python standard library with HTML escaping against XSS; zero external fonts or stylesheets.
