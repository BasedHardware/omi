# Export action items to Asana (CSV)

Use this recipe to export Omi action items into a CSV spreadsheet formatted for
direct import into [Asana](https://asana.com/) (`Project menu -> Import -> CSV`).

It maps action items to standard Asana task fields: task name, full description
with capture context, due dates, section/column status (`To Do` vs `Done`),
priority level, completion state (`TRUE`/`FALSE`), and tags. It requires zero
external dependencies (pure Python standard library), handles multi-page exports
with automatic ID deduplication, and safeguards against path traversal.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

---

## 1. Export action items from Omi

Export your action items into JSON:

```bash
# Export all action items
omi action-item list --limit 100 --json > action_items.json

# Or export multiple pages
omi action-item list --limit 100 --offset 0 --json > page1.json
omi action-item list --limit 100 --offset 100 --json > page2.json
```

---

## 2. Generate the Asana CSV file

Run `action_items_to_asana.py` against your exported files:

```bash
# Basic export
python action_items_to_asana.py action_items.json -o asana_tasks.csv

# With custom timezone offset and default section
python action_items_to_asana.py action_items.json \
  -o asana_tasks.csv \
  --tz-offset "+07:00" \
  --section "Incoming Tasks"

# Only export open (uncompleted) tasks
python action_items_to_asana.py action_items.json \
  -o asana_open.csv \
  --filter-status open

# Combine multiple files with automatic deduplication
python action_items_to_asana.py page1.json page2.json -o asana_all.csv
```

---

## 3. Command options

| Option | Default | Description |
| :--- | :--- | :--- |
| `-o, --output` | `action_items_asana.csv` | Destination CSV file path |
| `--tz-offset` | `+00:00` | Local UTC offset format `+HH:MM` or `-HH:MM` |
| `--section` | `"To Do"` | Asana section name for open tasks |
| `--filter-status` | `None` | Filter by `open` or `completed` tasks |
| `--force` | `False` | Overwrite existing output file if it exists |

---

## 4. Importing into Asana

1. Open your project in Asana.
2. Click the project dropdown arrow next to the project name -> select **Import** -> **CSV**.
3. Choose your exported `asana_tasks.csv`.
4. Asana automatically recognizes standard columns (`Name`, `Description`, `Due Date`, `Section/Column`, `Priority`, `Completed`, `Tags`).
5. Click **Go to project** to view your imported tasks in Board, List, or Timeline view.

---

## 5. Automated Tests

Run the test suite:

```bash
python test_action_items_to_asana.py
```
