# Build an action-items digest (task velocity, completion rates, overdue analysis, and pending queue)

Use this recipe to track your personal productivity, task velocity, and follow-ups captured by Omi, without digging through raw JSON files: it turns one or more `action-item list` exports into an executive Markdown digest with completion rates, daily task logging timelines, overdue task warnings, and prioritized pending action queues.

It reads saved JSON exports or piped input via `stdin`, makes zero network requests, requires zero third-party dependencies (pure Python 3.10+ standard library), and writes one clean Markdown file suitable for Obsidian, Notion, Logseq, or weekly sprint retrospectives.

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli`

## 1. Export your action items

Export the tasks you want to summarise (up to 200 per page):

```sh
omi --json action-item list --limit 200 > tasks.json
```

If you have accumulated more than 200 tasks across multiple weeks, retrieve subsequent pages into separate files. The digest tool accepts multiple files and automatically deduplicates entries by task ID:

```sh
omi --json action-item list --limit 200 --offset 0 > tasks_page1.json
omi --json action-item list --limit 200 --offset 200 > tasks_page2.json
```

## 2. Generate the digest

Run the companion converter script [`action_items_to_digest.py`](action_items_to_digest.py):

```sh
# Basic usage from a saved JSON export
python sdks/python-cli/examples/action_items_to_digest.py tasks.json tasks_digest.md

# Direct pipeline streaming via stdin
omi --json action-item list --limit 200 | python sdks/python-cli/examples/action_items_to_digest.py - tasks_digest.md

# Combine multiple files with a local timezone offset (e.g. UTC+8)
python sdks/python-cli/examples/action_items_to_digest.py tasks_page1.json tasks_page2.json weekly_digest.md --utc-offset +08:00

# Filter by a specific date window
python sdks/python-cli/examples/action_items_to_digest.py tasks.json september_tasks.md --since 2026-09-01T00:00:00Z --until 2026-09-30T23:59:59Z
```

### CLI Options

| Argument | Description | Default |
|:---|:---|:---|
| `SOURCE ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `DESTINATION` | Destination path for the Markdown file | *(required)* |
| `--utc-offset` | UTC offset for local day grouping (`+HH:MM` or `-HH:MM`) | `+00:00` |
| `--title` | Custom header title for the digest | `"Omi Action Items Digest"` |
| `--since` | ISO timestamp lower bound (e.g. `2026-09-01T00:00:00Z`) | None |
| `--until` | ISO timestamp upper bound (e.g. `2026-09-30T23:59:59Z`) | None |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

## 3. Sample output

The generated digest provides a high-level summary followed by structured breakdowns:

```markdown
# Weekly Sprint Action Items Digest

**Total Tasks**: 18 · **Completed**: 12 · **Pending**: 6 · **Completion Rate**: 66.7%
> ⚠️ **Overdue Tasks Attention Required**: 1 pending task(s) are past their due date.

## Productivity Summary

| Metric | Value |
|:---|---:|
| Total Action Items | 18 |
| Completed Items | 12 (66.7%) |
| Pending Items | 6 (33.3%) |
| Overdue Items | 1 |
| Active Days | 4 |
| Timeframe | 2026-09-18 to 2026-09-24 |

## Daily Task Timeline

| Date | Tasks Logged | Completed | Pending | Velocity |
|:---|---:|---:|---:|---:|
| 2026-09-24 | 5 | 3 | 2 | 60% |
| 2026-09-22 | 6 | 4 | 2 | 67% |
| 2026-09-20 | 4 | 3 | 1 | 75% |
| 2026-09-18 | 3 | 2 | 1 | 67% |

## ⚠️ Overdue Action Items

- [ ] **[OVERDUE: 2026-09-23]** Submit quarterly grant expenditure report `(ID: a1b2c3d4)`

## Pending Action Queue

- [ ] Email Alice design tokens draft *(Due: 2026-09-25)* `(ID: e5f6g7h8)`
- [ ] Schedule follow-up discussion on API rate limit architecture `(ID: 9i0j1k2l)`
- [ ] Review PR #18538 for SQLite schema compatibility `(ID: 3m4n5o6p)`

## Recently Completed Highlights

- [x] ~~Deploy Prometheus monitoring exporter to production~~ `(ID: 7q8r9s0t)`
- [x] ~~Fix timezone offset edge case in CLI date parser~~ `(ID: 1u2v3w4x)`
```

## 4. Integration Tips

- **Obsidian / Logseq Vaults**: Output the digest directly into your `Vault/Daily Notes/` or `Vault/Sprint Reviews/` folder.
- **Automated Cron Velocity Reports**: Run an end-of-week cron job every Friday:
  ```sh
  omi --json action-item list --limit 500 | python sdks/python-cli/examples/action_items_to_digest.py - ~/Vault/Weekly/tasks-$(date +%Y-W%V).md --utc-offset +08:00 --force
  ```
- **Automated Verification**: Run the automated test suite with:
  ```sh
  python sdks/python-cli/tests/test_action_items_to_digest.py
  ```
