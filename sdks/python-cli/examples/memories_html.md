# Build a self-contained HTML knowledge base of your memories

Convert Omi memories JSON exports into a clean, searchable HTML knowledge base and personal wiki with category grouping, emoji badges, statistics, and print-ready styles with zero external dependencies.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

### Export directly via CLI pipeline

```sh
omi --json memory list | python memories_to_html.py - -o wiki.html
```

### Export from a saved JSON file

```sh
python memories_to_html.py memories.json -o wiki.html
```

### Merging multiple export pages

```sh
python memories_to_html.py page1.json page2.json -o all_memories.html
```

## Running the Bundled Script

You can run the bundled recipe directly:

```sh
python sdks/python-cli/examples/memories_to_html.py memories.json -o wiki.html
```

## Features

- **Categorized Personal Wiki**: Groups memories into Work & Career, Skills & Tech, Learnings & Knowledge, User Preferences, Habits, and Core Facts.
- **Metric Cards**: Tracks Total Memories, Categories Count, Manual Notes, and Auto-Captured Knowledge.
- **Tagging & Badging**: Distinguishes manually created notes from background auto-extracted facts.
- **Print & PDF Support**: Built-in `@media print` rules ensure clean rendering for paper printing, PDF generation, or offline reading.
- **Safe & Self-Contained**: 100% Python standard library with HTML escaping against XSS; zero external fonts or stylesheets.
