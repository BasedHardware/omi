# Export Omi conversations to an Obsidian notes vault

Use this recipe to export your Omi conversations into an Obsidian notes vault. It structures conversations into chronological subfolders (`Conversations/YYYY-MM/`), attaches YAML frontmatter metadata, formats transcripts with Obsidian callouts, and creates a master index note with wiki-links.

## Vault Structure

```
OmiVault/
├── Conversations_Index.md
└── Conversations/
    └── 2026-09/
        ├── 2026-09-24-design-discussion.md
        └── 2026-09-25-weekly-sync.md
```

## Frontmatter Schema

Each note includes frontmatter for Dataview and graph navigation:

```yaml
---
id: "conv-123"
title: "Design Discussion"
date: 2026-09-24
category: work
speakers:
  - "Alice"
  - "Bob"
tags:
  - omi
  - conversation
  - omi/work
---
```

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export and build the vault in one command:

```sh
omi --json conversation list --limit 100 | python conversations_to_obsidian.py - -o ./OmiVault
```

Or convert a saved export file:

```sh
python conversations_to_obsidian.py conversations.json -o ~/Documents/Obsidian/OmiVault
```

Output:
```
Exported 35 conversation notes into Obsidian vault at /Users/.../Obsidian/OmiVault
```

## Features

- **Chronological Hierarchy**: Organizes notes into `YYYY-MM` folders to prevent flat directory sprawl.
- **Obsidian Callouts**: Formats summaries inside native `> [!summary]` callout blocks.
- **Master Wiki-Link Index**: Generates `Conversations_Index.md` with table of all meetings and internal `[[links]]`.
- **Pure Standard Library**: Zero external dependencies required.
