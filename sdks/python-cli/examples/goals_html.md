# Build a Self-Contained HTML Dashboard of Your Goals

Use this recipe to track, visualize, and review your Omi goals in a responsive HTML dashboard.
It converts one or more `goal list` JSON exports into a single standalone HTML report featuring an executive
KPI metrics grid (total goals, active goals, completed goals, and overall average progress), color-coded progress bars,
status badges (`active`, `completed`, `inactive`), and structured metric ranges with unit labels.

The dashboard is 100% self-contained: it makes no network requests, embeds all necessary responsive CSS styling
(with automatic light and dark mode support), and contains no external scripts or images.

---

## Prerequisites

You need Python 3.10+ and an authenticated `omi-cli` installed:

```sh
pip install omi-cli
omi auth login
```

Export your tracked goals (including completed and inactive milestones). Note that `omi goal list` caps
exports at `--limit 100` and currently provides no pagination offset, so accounts with more than 100 goals
will export the newest 100 records:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Verify that the export file was populated before running the converter. You can combine multiple exports
(e.g. from team members or historical snapshots); the converter deduplicates goals by their unique ID.

---

## Quickstart

### 1. Direct Pipeline Stream (Stdout)

Generate the HTML dashboard directly from the CLI output stream into stdout:

```sh
set -o pipefail
omi --json goal list --limit 100 --include-inactive | python goals_to_html.py -
```

### 2. Export to a Dedicated Dashboard File

Write the self-contained HTML report to a standalone file:

```sh
python goals_to_html.py goals.json -o ~/Reports/goals_dashboard.html
```

### 3. Filter by Goal Status

Generate a dashboard focused strictly on active milestones:

```sh
python goals_to_html.py goals.json --status active -o ~/Reports/active_goals.html
```

### 4. Custom Dashboard Title

Provide an executive title for your dashboard report:

```sh
python goals_to_html.py goals.json --title "Q4 Strategic OKRs" -o okrs.html
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more JSON export files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Destination HTML report file path | `stdout` |
| `--status` | `--status` | Filter goals by status (`all`, `active`, `completed`, `inactive`) | `all` |
| `--title` | `--title` | Custom report document title and heading | `"Omi Goals & Progress Dashboard"` |
| `--overwrite` | `--overwrite` | Allow overwriting existing destination files | `False` |

---

## Dashboard Output Preview

Here is an illustrative snippet of the generated HTML dashboard structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Omi Goals & Progress Dashboard</title>
  <style>/* Clean, responsive system-ui and dark/light mode styling */</style>
</head>
<body>
  <h1>Omi Goals & Progress Dashboard</h1>
  <p class="summary">Generated on 2026-10-02 07:30 UTC. Tracking 3 goals.</p>

  <div class="stats-grid">
    <div class="stat-card"><div class="num">3</div><div class="lbl">Total Goals</div></div>
    <div class="stat-card"><div class="num">2</div><div class="lbl">Active</div></div>
    <div class="stat-card"><div class="num">1</div><div class="lbl">Completed</div></div>
    <div class="stat-card"><div class="num">65.0%</div><div class="lbl">Avg Progress</div></div>
  </div>

  <h2>Goal Tracking</h2>
  <div class="goal-card">
    <div class="goal-header">
      <div class="goal-title">Read 20 Books<span class="type-tag">numeric</span></div>
      <span class="badge badge-active">active</span>
    </div>
    <div class="progress-container">
      <div class="progress-bar" style="width: 60.0%"></div>
    </div>
    <div class="goal-meta">
      <span>Progress: <strong>60.0%</strong> (12 / 20 books)</span>
      <span class="goal-id">goal_01</span>
    </div>
  </div>
</body>
</html>
```
