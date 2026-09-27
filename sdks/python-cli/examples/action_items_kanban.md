# Export action items to an Obsidian-compatible Markdown Kanban board

Use this recipe to convert Omi action items and tasks into an interactive Markdown Kanban board. The generated file includes standard YAML frontmatter recognized by the **Obsidian Kanban plugin**, Logseq, and Notion Markdown importers.

It categorizes tasks into three visual columns:
- **📅 Due / Scheduled**: Active tasks with deadlines (`@YYYY-MM-DD`).
- **📋 To Do**: Open backlog tasks without set dates.
- **✅ Done**: Completed tasks with checked Markdown boxes (`- [x]`).

## Exporting Action Items

Fetch action items with `omi-cli`:

```bash
omi --json action-item list --limit 200 > action_items.json
```

Or pipe directly into the converter:

```bash
omi --json action-item list | python action_items_to_kanban.py - -o ~/vault/Kanban.md
```

## Running the Exporter

Convert saved JSON exports to a Kanban board:

```bash
python action_items_to_kanban.py action_items.json -o Kanban.md
```

Custom board title:

```bash
python action_items_to_kanban.py action_items.json -o SprintBoard.md --title "Sprint 42 Tasks"
```

## Opening in Obsidian

1. Install the **Kanban plugin** in Obsidian (Community Plugins -> Kanban).
2. Save or copy `Kanban.md` into your Obsidian vault folder.
3. Open the note—Obsidian automatically renders it as an interactive drag-and-drop Kanban board!
