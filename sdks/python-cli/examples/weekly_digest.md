# Generate an executive weekly conversation digest

Use this recipe to group exported conversations by date and generate a clean Markdown executive summary complete with per-meeting summaries and action item checklists.

Export recent conversations:

```sh
omi --json conversation list --limit 100 > conversations.json
```

Generate digest:

```sh
python conversations_to_weekly_digest.py conversations.json weekly_digest.md
```

The resulting `weekly_digest.md` can be reviewed directly in Obsidian, GitHub, or any Markdown viewer.
