# Build an executive Markdown digest of your goals

Use this recipe to track your personal or team milestones, targets, and progress at a glance without reading raw JSON files or managing complex spreadsheet setups: it turns one or more `goal list` exports into a clean, executive Markdown digest featuring top-level KPI metrics, a breakdown by goal type, and an ASCII-visualized progress table.

It reads saved JSON exports, makes zero network requests, and generates a self-contained Markdown file ready for Obsidian notes, GitHub READMEs, Notion, or terminal previews.

## Prerequisites

- Python 3.9+
- An authenticated `omi-cli` session (`omi auth login`)

## 1. Export your goals

Export your active and archived goals using the CLI:

```sh
omi --json goal list > goals.json
```

If you manage a large collection of goals across multiple pagination windows, export each page with `--offset`:

```sh
omi --json goal list --limit 100 --offset 0 > goals_page1.json
omi --json goal list --limit 100 --offset 100 > goals_page2.json
```

## 2. Generate the Markdown digest

Run `goals_digest.py` by providing your exported JSON files:

```sh
python goals_digest.py goals.json -o GOALS_DIGEST.md
```

### Direct terminal pipeline (streaming)

You can stream directly from the Omi CLI through Unix pipes without creating intermediate JSON files:

```sh
omi --json goal list | python goals_digest.py - -o GOALS_DIGEST.md --force
```

### Multi-page aggregation and deduplication

When passing multiple files from paginated exports, `goals_digest.py` automatically merges records and deduplicates by `id`, keeping the most recently updated entry:

```sh
python goals_digest.py goals_page1.json goals_page2.json -o monthly_digest.md --force
```

### Filtering by status or type

To focus on active goals or specific measurement categories:

```sh
# Only display active goals
python goals_digest.py goals.json --status active -o active_goals.md

# Only summarize numeric metrics (e.g. running mileage, book counts)
python goals_digest.py goals.json --type numeric -o metrics_digest.md
```

## Example output

```markdown
# Omi Goals Executive Digest

> Generated on **2026-09-30 18:30:00 UTC** • Total Records Evaluated: **6**

## Executive Summary

| Metric | Count | Percentage |
| :--- | :--- | :--- |
| 🎯 **Total Goals** | `6` | `100.0%` |
| 🟢 **Active Goals** | `4` | `66.7%` |
| ✅ **Achieved Goals** | `2` | `33.3%` |
| ⚪ **Inactive Goals** | `0` | `0.0%` |
| 📊 **Average Progress** | `[========....] 68.3%` | `68.3%` |

## Breakdown by Goal Type

| Goal Type | Total | Achieved | Avg Progress |
| :--- | :--- | :--- | :--- |
| `boolean` | 2 | 1 (50.0%) | `[=====.....] 50.0%` |
| `numeric` | 2 | 1 (50.0%) | `[========..] 78.5%` |
| `scale` | 2 | 0 (0.0%) | `[=======...] 70.0%` |

## Goal Details

| Status | Title | Type | Progress | Target | Last Updated |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ✅ Achieved | Read 20 books | `numeric` | `[==========] 100.0%` | 20 / 20 books | 2026-09-28 |
| ✅ Achieved | Complete annual health check | `boolean` | `[==========] 100.0%` | 1 / 1 | 2026-09-15 |
| 🟢 Active | Daily 10k steps | `scale` | `[========..] 85.0%` | 8500 / 10000 steps | 2026-09-30 |
| 🟢 Active | Marathon training distance | `numeric` | `[======....] 57.0%` | 57 / 100 km | 2026-09-29 |
| 🟢 Active | Learn conversational Spanish | `boolean` | `[..........] 0.0%` | 0 / 1 | 2026-09-20 |
| 🟢 Active | Weekly meditation hours | `scale` | `[======....] 55.0%` | 5.5 / 10 hours | 2026-09-27 |
```

## Command line options

| Option | Default | Description |
| :--- | :--- | :--- |
| `sources` | _(required)_ | One or more input JSON file paths, or `-` for stdin. |
| `-o`, `--output` | `-` (stdout) | Destination path for the Markdown output file. |
| `-f`, `--force` | `False` | Overwrite existing destination file if present. |
| `--title` | `Omi Goals Executive Digest` | Custom title header in the digest output. |
| `--status` | `all` | Filter by status: `all`, `active`, `achieved`, `inactive`. |
| `--type` | `all` | Filter by goal type (e.g. `scale`, `numeric`, `boolean`, or `all`). |

## Security & hygiene guarantees

1. **Markdown Table Hygiene**: Raw strings from user input or speech transcripts often contain pipes (`|`) or multiline breaks. `goals_digest.py` automatically sanitizes pipe delimiters (`\|`) and collapses whitespace, ensuring Markdown tables render reliably across Obsidian, GitHub, and Notion.
2. **Path Traversal Protection**: Refuses any destination output path containing traversal segments (`..`) to safeguard local directories.
3. **Atomic Writes**: Uses safe temporary-file writes and atomic renames to prevent partially written or corrupted files if execution is interrupted.
4. **Air-Gapped & Offline**: 100% standard library code; executes locally with zero external network dependencies.
