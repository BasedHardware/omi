# Export memories to Obsidian vault Markdown

Use this recipe to export Omi device memories into an Obsidian knowledge vault with YAML frontmatter, tags, category headers, and [[wikilinks]].

Export memories:

```sh
omi --json memory list --limit 100 > memories.json
```

Convert to Obsidian:

```sh
python memories_to_obsidian.py memories.json omi_memories.md
```
