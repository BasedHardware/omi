# Export goals to Markdown notes and dashboards

Convert Omi goals JSON exports to clean Markdown notes for Obsidian, Notion, Logseq, or personal task dashboards.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` installation (or exported JSON file)

## Quick Start

### Export to a single Markdown dashboard

Pipe goals directly from the CLI into a formatted dashboard overview:

```sh
omi --json goal list | python goals_to_markdown.py - -o ~/vault/Goals.md
```

### Export into individual notes in an Obsidian vault

Organize goals into individual note files with YAML frontmatter tags:

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/
```

### Filter active goals only

```sh
omi --json goal list | python goals_to_markdown.py - --active-only -o ~/vault/ActiveGoals.md
```

## Running the Bundled Script

You can execute the bundled recipe directly:

```sh
python sdks/python-cli/examples/goals_to_markdown.py goals.json -o Goals.md
```

## Dashboard Features

- **Visual Progress Bar**: Dynamic Unicode bars with percentage indicators (e.g. `[████████░░] 80.0%`).
- **Status Badges**: Automatically categorizes goals into `🟢 Active`, `🏁 Completed`, and `⚪ Inactive`.
- **Target Metrics**: Displays current vs target values with units (e.g. `15 / 20 books`).
- **Frontmatter Metadata**: Each note includes Obsidian/Notion-compatible YAML frontmatter tags (`omi/goal`, `omi/goal/<type>`).
