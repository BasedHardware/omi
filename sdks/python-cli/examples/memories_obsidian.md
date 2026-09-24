# Export memories to an interconnected Obsidian knowledge vault

Use this recipe to transform raw Omi memories into a complete, interconnected Obsidian knowledge vault ("Second Brain"). Rather than dumping all facts into a single flat file, it constructs a networked knowledge graph complete with:
- **`Index.md` (Map of Content)**: Top-level hub with vault statistics and links to all category clusters.
- **`Categories/<Category>.md`**: Dedicated category hub notes grouping related memories.
- **`Memories/<slug>.md`**: Atomic concept notes with YAML frontmatter, tags (`#omi`, `#cat/...`), and bidirectional `[[WikiLinks]]`.

## Exporting Memories

Fetch memories with `omi-cli`:

```bash
omi --json memory list --limit 200 > memories.json
```

Or pipe directly into the vault builder:

```bash
omi --json memory list | python memories_to_obsidian.py - -o ~/Documents/Obsidian/SecondBrain/
```

## Running the Vault Builder

Generate an Obsidian vault directory from saved JSON exports:

```bash
python memories_to_obsidian.py memories.json -o ./OmiVault/
```

Customize the vault title in the Map of Content:

```bash
python memories_to_obsidian.py memories.json -o ./OmiVault/ --vault-name "Alex's Personal Mind"
```

## Opening the Vault in Obsidian

1. Open **Obsidian**.
2. Click **Open folder as vault** and choose the generated directory (e.g. `./OmiVault/`).
3. Open the **Graph View** (`Ctrl+G` / `Cmd+G`) to see your Omi memories visualized as an interactive knowledge network!
