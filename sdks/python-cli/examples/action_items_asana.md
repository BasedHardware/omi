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

Export your action items into JSON (note that `--json` is a global flag before the verb):

```bash
# Export all action items
omi --json action-item list --limit 100 > action_items.json

# Or export multiple pages
omi --json action-item list --limit 100 --offset 0 > page1.json
omi --json action-item list --limit 100 --offset 100 > page2.json
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
  --tz-offset "+09:00" \
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
| `--tz-offset` | `+00:00` | Timezone offset for local due dates (`+HH:MM` or `-HH:MM`) |
| `--section` | `To Do` | Default Asana section for open tasks |
| `--filter-status` | `None` | Filter tasks: `open` or `completed` |
| `--force` | `False` | Overwrite destination file if it already exists |

---

## 4. Importing into Asana

1. Open your project in Asana.
2. Click the project dropdown arrow next to the project title.
3. Select **Import** -> **CSV**.
4. Upload your generated `asana_tasks.csv`.
5. Verify column mappings (Name, Due Date, Section/Column, Priority, Assignee/Tags) and click **Import**.

---

## 5. Automated Tests

Run the test suite:

```bash
python -m pytest tests/test_action_items_to_asana.py
```
