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

To export directly to your Obsidian vault daily notes directory:

```sh
omi --json local recap --days-ago 0 | python local_recap_to_markdown.py - -o ~/Vault/Daily/2026-09-24.md --force
```

> **Note**: The converter protects against accidental overwrites by default. When updating an existing note for the day, pass `--force`.
> To omit the frontmatter block when embedding into an existing template, add `--no-frontmatter`.

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--no-frontmatter` | Omit YAML frontmatter block | `false` |
| `--title` | Custom note heading | `Daily Recap — YYYY-MM-DD` |

## Generated Markdown structure

The generated note maps the Desktop `sections` and `totals` into structured Markdown:

```markdown
---
date: "2026-09-24"
type: "omi-daily-recap"
apps_count: 2
tasks_count: 2
conversations_count: 1
focus_count: 1
generated_at: "2026-09-24T12:00:00Z"
tags:
  - omi/recap
  - journal/daily
---

# Daily Recap — 2026-09-24

## Overview
Productive sprint day focused on client-side exporters and automated test verification.

## Tasks & Action Items
- [ ] Implement vector batch ingestion pipeline `[HIGH]` — Refactor points payload structure
- [x] Pass all end-to-end integration tests

## App Usage & Focus
| Application | Active Time | Captures | First / Last Seen |
| :--- | :--- | :--- | :--- |
| **Safari** | 180.5m | 40 | 09:00:00Z - 17:30:00Z |
| **VS Code** | 120.0m | 25 | 10:15:00Z - 16:45:00Z |

## Focus Sessions
- **Deep Work** (60m) — *completed*

## Conversations & Discussions
- **Team Standup** (15m): Reviewed sprint backlog and release targets.

## Key Insights & Memories
- Explored zero-copy array operations for memory pipeline
```
