# Export Omi Desktop daily recap to structured Markdown

Use this recipe to turn Omi Desktop's daily screen and activity recap into structured
Markdown notes for Obsidian, Notion, or personal daily journals. It reads JSON
exports from `omi local recap`, makes no network requests during conversion, and
produces clean, human-readable Markdown with optional YAML frontmatter.

The companion script [`local_recap_to_markdown.py`](local_recap_to_markdown.py) runs
on Python 3.10+ using only standard library modules (`json`, `argparse`, `datetime`).

## 1. Export local recap from Omi Desktop

Export today's desktop activity recap in JSON format:

```sh
omi --json local recap --days-ago 0 > today.json
```

Or export yesterday's recap:

```sh
omi --json local recap --days-ago 1 > yesterday.json
```

## 2. Convert to Markdown notes

Run the converter to generate a daily note:

```sh
python local_recap_to_markdown.py today.json -o 2026-09-24.md
```

Or pipe directly from `omi-cli`:

```sh
omi --json local recap --days-ago 0 | python local_recap_to_markdown.py - -o today.md
```

### Obsidian daily notes integration

To append directly to an Obsidian vault without frontmatter:

```sh
omi --json local recap --days-ago 0 | python local_recap_to_markdown.py - --no-frontmatter -o ~/Vault/Daily/2026-09-24.md
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--no-frontmatter` | Omit YAML frontmatter block | `false` |
| `--title` | Custom note heading | `Daily Recap — YYYY-MM-DD` |

## Generated Markdown structure

The generated note organizes local activity into clear sections:

```markdown
---
date: "2026-09-24"
type: "omi-daily-recap"
highlights_count: 2
apps_count: 2
generated_at: "2026-09-24T12:00:00Z"
tags:
  - omi/recap
  - journal/daily
---

# Daily Recap — 2026-09-24

## Overview
Focused on core backend services and shipping pull requests.

## Key Highlights
- [x] Implemented vector batch ingestion pipeline
- [x] Passed all end-to-end integration tests

## App Usage & Focus
| Application | Duration | Notes |
| :--- | :--- | :--- |
| **VS Code** | 180m | Coding & refactoring |
| **Terminal** | 45m | CI & local testing |

## Activity Timeline
* **09:00**: Morning triage and sprint review
* **14:00**: Feature development and verification
```
