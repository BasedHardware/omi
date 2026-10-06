# Convert a goals export to CSV

Use this recipe to review your Omi goals and targets in spreadsheets or text pipelines.
It reads a saved JSON export, makes no network requests, and generates a standard CSV
file with progress metrics, formula injection defense, and clean numeric types.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export. Pure
standard library only — zero extra dependencies.

## Step 1: Export goals

Export both active and inactive goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

> **Note**: `goal list` defaults to active goals only. Passing `--include-inactive`
> ensures both active and completed/archived goals are included in your spreadsheet.

## Step 2: Convert to CSV

Run the converter script [`goals_to_csv.py`](goals_to_csv.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/goals_to_csv.py goals.json -o goals.csv
```

To overwrite an existing CSV file:

```sh
python sdks/python-cli/examples/goals_to_csv.py goals.json -o goals.csv --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json goal list --limit 100 --include-inactive | python sdks/python-cli/examples/goals_to_csv.py - -o goals.csv
```

## CSV Columns & Structure

| Column | Description / Behavior |
|---|---|
| `id` | Goal identifier; preserves leading zeros. |
| `title` | Formula injection protected; values starting with `=`, `+`, `-`, `@` are prefixed with `'`. |
| `goal_type` | Goal classification (`boolean`, `scale`, `numeric`). |
| `target_value` | Numeric target threshold. |
| `current_value` | Current progress value. |
| `min_value` | Numeric lower bound for scale goals. |
| `max_value` | Numeric upper bound for scale goals. |
| `unit` | Measurement unit (e.g. `hours`, `pages`, or empty). |
| `is_active` | `true` or `false` active status string. |
| `progress_pct` | Calculated completion percentage (`0.0%` to `100.0%`). |
| `created_at` | ISO 8601 creation timestamp. |
| `updated_at` | ISO 8601 update timestamp. |

## Security & Reliability Invariants

- **Formula Injection Mitigation**: Text cells starting with `=`, `+`, `-`, or `@` are safely escaped with a leading apostrophe (`'`), preventing malicious spreadsheet formulas from executing upon CSV import.
- **Progress Normalization**: Safely calculates percentage for scale, boolean, and numeric goal types, protecting against division by zero.
- **Atomic File Writing**: Writes output to a `.partial` file before atomically replacing destination via `os.replace`.
- **Path Traversal Protection**: Rejects destination paths containing `..` components.
