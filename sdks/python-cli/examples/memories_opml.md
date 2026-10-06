# Export Omi Memories to OPML 2.0 (Workflowy / Logseq / OmniFocus / Dynalist)

Use this recipe to export and synchronize facts, learnings, and memories captured by your Omi wearable device into clean **OPML 2.0** outlines. The resulting documents are optimized for hierarchical outliners and second-brain systems including **Workflowy**, **Logseq**, **OmniFocus**, and **Dynalist**.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your memories:

```sh
omi memory list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdin)

Generate an OPML outline directly from the CLI output stream:

```sh
omi --json memory list --limit 200 | python memories_to_opml.py - memories.opml
```

### 2. Export with Category Grouping (Default)

Organize memories into structured parent outlines based on their category (e.g. *Work*, *Skills*, *Lifestyle*, *Learnings*):

```sh
python memories_to_opml.py memories.json memories.opml
```

### 3. Flat Export (No Category Parent Nodes)

Export memory items as root-level outline elements without grouping:

```sh
python memories_to_opml.py memories.json memories.opml --flat
```

### 4. Filter by Specific Categories

Export only specific categories of interest:

```sh
python memories_to_opml.py memories.json memories.opml --category work,skills
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | Path to JSON file, or `-` for stdin | *(Required)* |
| `output` | Position 2 | Path to destination OPML file | *(Required)* |
| `--category` | `-c` | Filter by comma-separated categories (e.g. `work,skills`) | `None` (all) |
| `--flat` | `--flat` | Export flat list without category outline grouping | `False` |

---

## Output Structure

### Sample OPML 2.0 Document (`memories.opml`)

```xml
<?xml version='1.0' encoding='UTF-8'?>
<opml version="2.0">
  <head>
    <title>Omi Memories</title>
    <dateCreated>2026-10-06T18:00:00+00:00</dateCreated>
  </head>
  <body>
    <outline text="Lifestyle">
      <outline text="Alex prefers dark roast coffee" created="2026-10-06T12:00:00Z" category="lifestyle" _tags="#coffee #preferences" _visibility="public" _id="mem_01" />
    </outline>
    <outline text="Skills">
      <outline text="Learned Rust lifetimes and memory safety models" created="2026-10-06T14:30:00Z" category="skills" _tags="#rust #systems" _visibility="private" _id="mem_02" />
    </outline>
    <outline text="Work">
      <outline text="Leading the TypeScript SDK integration and CLI tooling initiative" created="2026-10-06T16:15:00Z" category="work" _tags="#typescript #devtools" _visibility="public" _id="mem_03" />
    </outline>
  </body>
</opml>
```

---

## Outliner Import Workflows

### Workflowy
1. In Workflowy, click the **Settings** menu or open a parent node.
2. Select **Import** $\rightarrow$ **OPML**.
3. Upload `memories.opml`. Your categories and memory items will be imported as interactive nested bullet trees.

### Logseq
1. In Logseq, click the **...** menu in the top right.
2. Select **Import** $\rightarrow$ **OPML**.
3. Select `memories.opml` to populate a dedicated outline page in your local graph.

### OmniFocus / Dynalist
1. Drag and drop `memories.opml` into the application or use File $\rightarrow$ Import OPML.

---

## Design Principles

- **Zero External Dependencies:** Built using Python standard library only (`xml.etree.ElementTree`, `json`, `argparse`, `pathlib`, `re`, `datetime`).
- **Surrogate Safe:** Automatically drops unpaired surrogate code points (`\ud800`–`\udfff`) from voice transcripts to guarantee valid UTF-8 XML encoding.
- **Atomic File Writing:** Writes to a `.partial` file before atomic rename, preventing corrupted partial writes.
- **Envelope Coercion:** Accepts bare lists `[...]`, standard envelopes `{"memories": [...]}`, or CLI output streams.
