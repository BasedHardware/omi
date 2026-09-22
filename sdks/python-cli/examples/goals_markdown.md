# Export goals to Markdown notes & dashboard

Use this recipe to integrate your Omi tracked goals into your Second Brain
(Obsidian, Notion, Logseq). It converts saved JSON exports into structured
Markdown files with YAML frontmatter for Obsidian Dataview, or renders a
consolidated dashboard with ASCII progress bars.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export tracked goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Generate individual Markdown notes in your vault:

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/
```

Or generate a single visual goals dashboard note:

```sh
omi --json goal list | python goals_to_markdown.py - --dashboard ./vault/goals_dashboard.md
```

Each generated note includes structured YAML frontmatter:

```yaml
---
id: "goal_123"
title: "Run 50km this month"
goal_type: "numeric"
current_value: 35.0
target_value: 50.0
unit: "km"
is_active: true
tags:
  - omi
  - goal
  - active
---
```

Use Obsidian Dataview to list your active goals:

````markdown
```dataview
TABLE current_value as Current, target_value as Target, unit as Unit
FROM #goal AND #active
SORT file.name ASC
```
````
