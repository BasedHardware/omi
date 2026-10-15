# Build a Self-Contained HTML Report of Your Conversations

Use this recipe to browse, archive, or print your Omi conversation history without the CLI or a spreadsheet.
It converts one or more `conversation list` JSON exports into a single, clean HTML report featuring an executive
metrics grid, one chronological section per calendar day, and a structured table of recorded sessions (start time,
duration, title, category tag, folder, source device, language, and conversation ID).

The report is 100% self-contained: it makes no network requests, embeds all necessary responsive CSS styling, and
contains no external scripts or images.

---

## Prerequisites

You need Python 3.10+ and an authenticated `omi-cli` installed:

```sh
pip install omi-cli
omi auth login
```

Export the period you want to report on (up to 200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 > week.json
```

Verify that the export file was populated before running the converter. This is one page; to retrieve more,
re-run with `--offset 200` (and so on) into separate files (e.g. `p1.json p2.json`) and pass them together.
The converter deduplicates records by their conversation ID.

---

## Quickstart

### 1. Direct Pipeline Stream (Stdout)

Generate the HTML report directly from the CLI output stream into stdout:

```sh
set -o pipefail
omi --json conversation list --limit 200 | python conversations_to_html.py -
```

### 2. Export to a Dedicated Report File

Write the self-contained HTML report to a standalone file:

```sh
python conversations_to_html.py week.json -o ~/Reports/week.html
```

### 3. Local Timezone Offset

Adjust clock times and daily section boundaries to your local timezone (e.g. Tokyo `+09:00` or New York `-05:00`):

```sh
python conversations_to_html.py week.json --utc-offset=-05:00 -o ~/Reports/week_est.html
```

### 4. Custom Report Title

Provide an executive title for your report:

```sh
python conversations_to_html.py week.json --title "Q3 Client Discovery Sessions" -o client_review.html
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more JSON export files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Destination HTML report file path | `stdout` |
| `--utc-offset` | `--utc-offset` | UTC offset (e.g. `+09:00` or `--utc-offset=-05:00`) | `+00:00` |
| `--title` | `--title` | Custom report document title and heading | `"Omi Conversation Report"` |
| `--overwrite` | `--overwrite` | Allow overwriting existing destination files | `False` |

---

## Report Output Preview

Here is an illustrative snippet of the generated HTML report structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Omi Conversation Report</title>
  <style>/* Clean, responsive system-ui and print styling */</style>
</head>
<body>
  <h1>Omi Conversation Report</h1>
  <p class="summary">Generated report with times shown in UTC+00:00.</p>
  <div class="stats-grid">
    <div class="stat-card"><div class="num">12</div><div class="lbl">Conversations</div></div>
    <div class="stat-card"><div class="num">3.5h</div><div class="lbl">Recorded Time</div></div>
    <div class="stat-card"><div class="num">4</div><div class="lbl">Active Days</div></div>
    <div class="stat-card"><div class="num">0</div><div class="lbl">Undated</div></div>
  </div>
  <h2 id="d2026-10-01">2026-10-01</h2>
  <p class="summary">3 conversations · 1.2 hours</p>
  <table>
    <thead><tr><th>Start</th><th>Duration</th><th>Title</th><th>Category</th>...</tr></thead>
    <tbody>
      <tr>
        <td class="num">09:00</td>
        <td class="num">30 min</td>
        <td><strong>Quarterly Planning & Review</strong></td>
        <td><span class="badge">work</span></td>
        ...
      </tr>
    </tbody>
  </table>
</body>
</html>
```

---

## Browser Viewing & Printing

1. Open the exported HTML file in any modern web browser:
   ```sh
   google-chrome ~/Reports/week.html
   ```
2. Press `Ctrl+P` (or `Cmd+P` on macOS) to export a clean, multi-page PDF or print directly to paper.
   The embedded `@media print` rules remove margins, avoid breaking table rows across pages, and format headers cleanly.

---

## Design Principles

- **Zero Third-Party Dependencies**: 100% Python standard library (`argparse`, `datetime`, `html`, `json`, `pathlib`).
- **Complete XSS Sanitization**: Every textual field and identifier is sanitized using `html.escape`.
- **Safe POSIX Permissions**: Creates output files with standard user permissions (`0644`).
- **Atomic File Operations**: Uses temporary file replacement and `os.fsync` when `--overwrite` is specified.
- **Piped Stream Hygiene**: Native `BrokenPipeError` signal handling for commands like `| head`.
