# Visualize Omi memories as a Graphviz knowledge graph

Use this recipe to convert Omi memories into standard Graphviz `.dot` format. It clusters memories by category into visual subgraphs with dates and previews, making it easy to see the structure of your personal knowledge base.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation
- Optional: Graphviz CLI (`dot`) for rendering to PNG/SVG/PDF, or use any online Graphviz viewer (e.g. [Edotor](https://edotor.net/))

## Usage

Generate a `.dot` file from your memories:

```sh
omi --json memory list --limit 100 | python memories_to_graphviz.py - -o memories.dot
```

Or process a local export:

```sh
python memories_to_graphviz.py memories.json -o memories.dot
```

## Rendering to Image

Convert the `.dot` graph to PNG using Graphviz:

```sh
dot -Tpng memories.dot -o memories.png
```

Or render directly to SVG:

```sh
dot -Tsvg memories.dot -o memories.svg
```

## Features

- **Category Clusters**: Organizes memories into distinct, color-coded subgraphs based on categories (e.g. `work`, `personal`, `preferences`).
- **Standard DOT Syntax**: Can be loaded into VS Code Graphviz previewers, Notion, Obsidian, and web diagram tools.
- **Pure Standard Library**: Zero external Python packages required.
