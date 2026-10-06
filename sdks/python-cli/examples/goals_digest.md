# Build an executive goals digest report

Use this recipe to summarize your tracked Omi goals into an executive Markdown digest report
with key performance indicators (total, active, achieved, inactive, average progress), type
distributions, and visual ASCII progress bars.

The script runs completely offline with Python's standard library and makes no network requests.

## Quickstart

### 1. Export your goals with omi-cli

Export your active and archived goals using the root `--json` flag:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

*Note: The CLI caps `--limit` at 100 goals. To include completed and paused goals, pass `--include-inactive`.*

### 2. Generate the digest report

Run the generator to create an executive summary report:

```sh
python sdks/python-cli/examples/goals_digest.py goals.json -o goals_digest.md
```

You can also stream directly via Unix pipes using `-`:

```sh
omi --json goal list --limit 100 --include-inactive | \
  python sdks/python-cli/examples/goals_digest.py - -o goals_digest.md
```

Multiple export files (e.g. from multiple accounts or historical backups) are merged and deduplicated
by goal ID, retaining the latest `updated_at` record:

```sh
python sdks/python-cli/examples/goals_digest.py Q1_goals.json Q2_goals.json -o annual_goals_digest.md
```

## Sample Output

The generated report features executive KPI summary cards and clean Markdown tables:

```markdown
# Omi Goals Executive Digest

> *Generated on 2026-10-06 18:00:00 UTC | Source: Omi CLI*

## Executive Summary

| Metric | Value |
|---|---|
| **Total Goals** | 4 |
| **Active Goals** | 3 |
| **Achieved Goals** | 1 |
| **Inactive / Paused** | 1 |
| **Average Progress** | 62.5% |

## Type Breakdown

| Goal Type | Count | Share |
|---|---|---|
| Numeric | 2 | 50.0% |
| Qualitative | 1 | 25.0% |
| Scale | 1 | 25.0% |

## Detailed Goals Status

| ID | Title | Type | Status | Progress |
|---|---|---|---|---|
| `g_run` | Run 100 km this month | numeric | **ACTIVE** | `[======    ]` 60.0% |
| `g_read` | Read 12 books | numeric | **ACTIVE** | `[===       ]` 30.0% |
| `g_deep` | Daily deep focus habit | qualitative | **ACHIEVED** | `[==========]` 100.0% |
| `g_med` | Morning meditation | scale | **PAUSED** | `[====      ]` 40.0% |
```

## Options Reference

| Option | Description |
|---|---|
| `inputs` | One or more input JSON files, or `-` for standard input streaming |
| `-o, --output` | Output destination file path (default: stdout) |
| `-f, --force` | Overwrite existing output destination without error |
| `--title` | Custom header title for the digest report |

## Security & Reliability Invariants

- **Strict Status Precedence**: Explicit inactive or paused statuses (`is_active=False`, `paused`, `abandoned`) strictly take precedence over `>=100%` progress to prevent completed labels on abandoned goals.
- **Table Cell Sanitization**: Backslashes and pipes (`|`) are safely escaped, and newlines/tabs are collapsed to single spaces to guarantee table layout columns never tear.
- **Path Traversal Protection**: Rejects input and output file paths containing `..` path segments.
- **Atomic Writing**: Writes to a temporary sibling file (`.tmp_digest_*.md`) before replacing the destination via `os.replace`, ensuring incomplete or interrupted writes never damage existing reports.
