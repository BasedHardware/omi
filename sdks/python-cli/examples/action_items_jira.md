# Convert an action items export to jira import CSV

Use this recipe to map a saved `omi --json action-item list` export into the CSV
shape jira's importer expects. The script makes no network requests; it reads
the local export and writes one CSV row per action item.

Export a page of action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Then run:

```sh
python action_items_to_jira.py action_items_0.json action_items_jira.csv
```

Import the CSV from jira's import UI. Verify the command exited 0 first — an
empty or partial export file is not a backup.
