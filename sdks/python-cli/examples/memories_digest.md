# Build a memory digest (daily totals, categories, tag trends, and key highlights)

Use this recipe to see how your second brain is growing and what knowledge Omi has captured, without manually reading through raw JSON files: it turns one or more `memory list` exports into a concise Markdown digest with daily totals, category distributions, top knowledge tags, and recent memory highlights.

It reads saved JSON exports or piped input via `stdin`, makes no network requests, requires zero third-party dependencies (pure Python 3.10+ standard library), and writes one clean Markdown file suitable for Obsidian, Notion, Logseq, or weekly personal retrospectives.

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli`

## 1. Export your memories

Export the memories you want to summarise (up to 200 per page):

```sh
omi --json memory list --limit 200 > memories.json
```

If you have accumulated more than 200 memories across multiple weeks, retrieve subsequent pages into separate files. The digest tool accepts multiple files and automatically deduplicates entries by memory ID:

```sh
omi --json memory list --limit 200 --offset 0 > memories_page1.json
omi --json memory list --limit 200 --offset 200 > memories_page2.json
```

## 2. Generate the digest

Run the companion converter script [`memories_to_digest.py`](memories_to_digest.py):

```sh
# Basic usage from a saved JSON export
python sdks/python-cli/examples/memories_to_digest.py memories.json memories_digest.md

# Direct pipeline streaming via stdin
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_digest.py - memories_digest.md

# Combine multiple files with a local timezone offset (e.g. UTC+8)
python sdks/python-cli/examples/memories_to_digest.py memories_page1.json memories_page2.json weekly_digest.md --utc-offset +08:00

# Filter by a specific date window
python sdks/python-cli/examples/memories_to_digest.py memories.json september_digest.md --since 2026-09-01T00:00:00Z --until 2026-09-30T23:59:59Z
```

### CLI Options

| Argument | Description | Default |
|:---|:---|:---|
| `SOURCE ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `DESTINATION` | Destination path for the Markdown file | *(required)* |
| `--utc-offset` | UTC offset for local day grouping (`+HH:MM` or `-HH:MM`) | `+00:00` |
| `--title` | Custom header title for the digest | `"Omi Memory Digest"` |
| `--since` | ISO timestamp lower bound (e.g. `2026-09-01T00:00:00Z`) | None |
| `--until` | ISO timestamp upper bound (e.g. `2026-09-30T23:59:59Z`) | None |
| `--top-tags` | Maximum number of top tags to rank in the summary table | `10` |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

## 3. Sample output

The generated digest provides a high-level summary followed by structured breakdowns:

```markdown
# Weekly Second Brain Digest

**Total Memories**: 24 · **Active Days**: 5 · **Timeframe**: 2026-09-15 to 2026-09-21

## Daily Activity

| Date | Memories Added | Primary Categories |
|:---|---:|:---|
| 2026-09-21 | 8 | `work` (5), `learnings` (3) |
| 2026-09-20 | 6 | `skills` (4), `preferences` (2) |
| 2026-09-18 | 4 | `work` (3), `general` (1) |
| 2026-09-16 | 4 | `learnings` (4) |
| 2026-09-15 | 2 | `preferences` (2) |

## Category Distribution

| Category | Count | Share | Key Tags |
|:---|---:|---:|:---|
| `work` | 10 | 41.7% | #backend, #api, #database |
| `learnings` | 7 | 29.2% | #python, #rust, #architecture |
| `skills` | 4 | 16.7% | #fastapi, #asyncio |
| `preferences` | 3 | 12.5% | #hardware, #editor |

## Top Knowledge Tags & Themes

| Tag | Mentions |
|:---|---:|
| `#backend` | 8 |
| `#python` | 7 |
| `#database` | 5 |
| `#architecture` | 4 |
| `#rust` | 3 |

## Recent Knowledge Highlights

- **[work]** Discussed migrating search pipeline to SQLite FTS5 for offline indexing #backend #database `(2026-09-21, ID: a1b2c3d4)`
- **[learnings]** Explored zero-copy deserialization techniques in high-throughput consumers #rust #architecture `(2026-09-21, ID: e5f6g7h8)`
- **[preferences]** Prefers 2-space YAML formatting and strict schema linting on commits #editor `(2026-09-20, ID: 9i0j1k2l)`
```

## 4. Integration Tips

- **Obsidian / Logseq Vaults**: Output the digest directly into your `Vault/Daily Notes/` or `Vault/Reviews/` folder.
- **Automated Cron Summaries**: Run a weekly cron job every Sunday night:
  ```sh
  omi --json memory list --limit 500 | python sdks/python-cli/examples/memories_to_digest.py - ~/Vault/Weekly/$(date +%Y-W%V).md --utc-offset +08:00 --force
  ```
- **Automated Verification**: Run the automated test suite with:
  ```sh
  python sdks/python-cli/tests/test_memories_to_digest.py
  ```
