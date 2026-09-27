# Convert a goals export to CSV

Use this recipe to review, filter, and analyze your tracked goals, habits, and progress metrics in a spreadsheet (Microsoft Excel, Google Sheets, Apple Numbers) or data science environment (Pandas, Polars, DuckDB).

It reads a saved JSON export from `omi goal list`, runs completely offline with zero network requests, and applies spreadsheet formula injection protection.

---

## Prerequisites

You need Python 3.9+ and an authenticated `omi-cli`:

```sh
pip install omi-cli
omi auth login
```

Verify you can query your goals:

```sh
omi goal list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout or Redirection)

Convert goals directly from the CLI JSON stream into a CSV file:

```sh
omi --json goal list | python goals_to_csv.py - -o goals.csv
```

### 2. Export Only Active Goals

Export open, ongoing goals to a dedicated spreadsheet:

```sh
omi --json goal list | python goals_to_csv.py - --active-only -o active_goals.csv
```

### 3. Convert Existing File

If you previously saved an export:

```sh
omi --json goal list --limit 100 > my_goals.json
python goals_to_csv.py my_goals.json -o my_goals.csv
```

---

## CSV Columns

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | String | Unique identifier for the goal |
| `title` | String | Title or description of the goal |
| `goal_type` | String | Metric type: `numeric`, `boolean`, or `scale` |
| `current_value` | Number | Current tracked progress value |
| `target_value` | Number | Target or completion value |
| `min_value` | Number | Baseline or minimum metric value |
| `max_value` | Number | Upper boundary metric value |
| `unit` | String | Unit of measurement (e.g. `pages`, `liters`, `hours`) |
| `progress_percent`| Float | Calculated completion percentage (`0.00` to `100.00`) |
| `is_active` | Boolean | `true` if in-progress; `false` if archived/completed |
| `created_at` | ISO-8601 | Timestamp when the goal was created |
| `updated_at` | ISO-8601 | Timestamp of latest progress update |

---

## Security: Spreadsheet Formula Injection Guard

Fields containing user-controlled text that begin with `=`, `+`, `-`, or `@` (or whitespace tabs/newlines) are automatically escaped with a leading apostrophe (`'`). This prevents spreadsheet software like Excel and Google Sheets from interpreting malicious strings as executable DDE or CSV formula payloads.
