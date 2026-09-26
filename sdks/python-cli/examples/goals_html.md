# Export goals to an offline HTML dashboard

The [goals_to_html.py](goals_to_html.py) recipe creates a self-contained dashboard with search, filters, progress cards, and browser printing. It uses Python's standard library. The HTML needs no network connection or server.

## Prerequisites

- Python 3.10 or newer.
- For live export only: `omi-cli` installed and already signed in under the profile you want to use. Demo and saved JSON modes do not use an account.
- Run these commands from the repository root.

## Try the demo first

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --demo --output dashboard.html
Start-Process .\dashboard.html
```

Bash:

```bash
python sdks/python-cli/examples/goals_to_html.py --demo --output dashboard.html
```

Open `dashboard.html` in a browser. Use **Print / Save PDF** and choose your browser's PDF destination. The dashboard remains usable offline.
Select a goal title to expand its details. With the title focused, press Enter or Space to toggle it. Printing includes details from collapsed cards too.

## Export your goals

Live export uses the installed Omi CLI and includes inactive goals:

```powershell
.\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --output dashboard.html
```

To select a profile, put `--profile` on the exporter command. It passes the option before `goal list`, as required by the CLI:

```powershell
.\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --profile work --output dashboard.html
```

If the CLI executable is elsewhere on Windows, specify it explicitly:

```powershell
.\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --omi-executable "C:\Users\YourName\AppData\Roaming\Python\Python313\Scripts\omi.exe" --output dashboard.html
```

The exporter first looks beside the running Python interpreter for `omi.exe` or `omi`, then falls back to `omi` on `PATH`. `--omi-executable` overrides that choice. It does not ask you to log in or inspect your credentials.

You can export a saved JSON array from `omi --json goal list --include-inactive`, or pass JSON on standard input. PowerShell examples:

```powershell
.\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --input goals.json --output dashboard.html
Get-Content goals.json -Raw | .\.venv\Scripts\python.exe sdks/python-cli/examples/goals_to_html.py --input - --output dashboard.html
```

Bash examples:

```bash
python sdks/python-cli/examples/goals_to_html.py --input goals.json --output dashboard.html
python sdks/python-cli/examples/goals_to_html.py --input - --output dashboard.html < goals.json
```

UTF-8 files with a BOM are accepted. `--demo` and `--input` cannot be combined. The exporter writes the destination only after retrieval, validation, and rendering succeed; a failed run leaves an existing dashboard intact.

## Reading the dashboard

The summary cards count the full exported dataset, even when filters hide cards. **Active** follows `is_active`; a `background` or `paused` goal can still be active. **Completed** means status `achieved`. `abandoned` is not completed, and reaching a numeric target does not change completion status. Completion rate is achieved goals divided by exported goals, or 0% when there are none.

For scale and numeric goals, the dashboard shows `current / target` and, when the target is positive and both numbers are finite, computes `current ÷ target × 100`. Boolean goals use 0 and 1 for current and target; a target of 1 produces 0% or 100%. Invalid boolean values, zero or negative targets, missing numbers, and non-finite numbers have an explanation instead of a percentage. The visual bar stays between 0% and 100%; the displayed numbers and calculated percentage can exceed the target or be negative. Qualitative goals show no invented metric or progress bar.

Goals have statuses `background`, `focused`, `paused`, `achieved`, and `abandoned`, plus metric types `boolean`, `scale`, and `numeric`. The CLI goal response does not provide an OKR hierarchy, so this recipe exports goals as individual cards.

## Snapshot scope and privacy

The HTML is an **offline snapshot** taken when the exporter runs. Live retrieval requests the latest **up to 100** goals including inactive ones. The CLI has no goal-list pagination, so a full 100-goal response may omit older goals. Saved JSON is shown exactly as supplied; its completeness depends on how it was collected. The dashboard labels this scope and never claims to contain every account goal.

The exported HTML contains personal goal titles and descriptions. Keep it private and avoid committing or sharing it unintentionally.

## Troubleshooting

- **CLI not found:** install `omi-cli` in the active Python environment, add it to `PATH`, or use `--omi-executable`.
- **CLI failed:** run `omi --json goal list --include-inactive --limit 100` directly to see the CLI diagnostic. For a named profile, place `--profile NAME` before `goal list`.
- **Invalid JSON or response:** supply a JSON array of goal objects with nonempty titles. The exporter reports malformed shapes instead of producing a partial page.
- **Cannot write output:** choose a writable destination directory. The exporter will not replace an existing output after a failed export.
- **Search or filters unavailable:** enable JavaScript in the browser. The goal cards remain readable without it.
