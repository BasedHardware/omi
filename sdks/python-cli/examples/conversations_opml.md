# Export Omi Conversations to OPML 2.0 (Workflowy / Logseq / OmniFocus / Dynalist)

Use this recipe to export and synchronize recorded conversations, meetings, and discussions captured by your Omi wearable device into clean **OPML 2.0** outlines. The resulting documents organize summaries, action items, and timestamped transcripts into expandable nested outliner trees optimized for **Workflowy**, **Logseq**, **OmniFocus**, and **Dynalist**.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your conversations:

```sh
omi conversation list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdin)

Generate an OPML outline directly from the CLI output stream:

```sh
omi --json conversation list --include-transcript --limit 50 | python conversations_to_opml.py - conversations.opml
```

### 2. Export a Saved JSON File

Convert an existing JSON export to OPML:

```sh
python conversations_to_opml.py conversations.json conversations.opml
```

### 3. Filter by Specific Categories

Export only specific categories (e.g. *work* and *meetings*):

```sh
python conversations_to_opml.py conversations.json conversations.opml --category work,meetings
```

### 4. Flat Outline Export

Export high-level conversation title nodes without nested subsections:

```sh
python conversations_to_opml.py conversations.json conversations.opml --flat
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | Path to JSON file, or `-` for stdin | *(Required)* |
| `output` | Position 2 | Path to destination OPML file | *(Required)* |
| `--category` | `-c` | Filter by comma-separated categories (e.g. `work,general`) | `None` (all) |
| `--flat` | `--flat` | Export flat list without nested outline sections | `False` |

---

## Output Structure

### Sample OPML 2.0 Document (`conversations.opml`)

```xml
<?xml version='1.0' encoding='UTF-8'?>
<opml version="2.0">
  <head>
    <title>Omi Conversations</title>
    <dateCreated>2026-10-06T18:00:00+00:00</dateCreated>
  </head>
  <body>
    <outline text="Quarterly Product Strategy" created="2026-10-06T15:30:00Z" category="work" _id="conv_01">
      <outline text="Overview: Discussed Q4 roadmap priorities and developer tooling." />
      <outline text="Action Items">
        <outline text="Publish OPML export recipe" _status="completed" />
        <outline text="Review PR benchmarks" _status="open" due="2026-10-10" />
      </outline>
      <outline text="Transcript">
        <outline text="[00:00] Speaker 0: Let's align on Q4 goals." />
        <outline text="[00:15] Speaker 1: Agreed, developer experience is top priority." />
      </outline>
    </outline>
  </body>
</opml>
```

---

## Outliner Import Workflows

### Workflowy
1. In Workflowy, open any parent page or click **Settings**.
2. Select **Import** $\rightarrow$ **OPML**.
3. Upload `conversations.opml`. Your conversations expand into interactive nested trees with overview, tasks, and dialogue turns.

### Logseq
1. In Logseq, click the **...** menu in the top right.
2. Select **Import** $\rightarrow$ **OPML**.
3. Select `conversations.opml` to create a dedicated conversation log in your graph.

### OmniFocus / Dynalist
1. Drag and drop `conversations.opml` directly into the app or use File $\rightarrow$ Import.

---

## Design Principles

- **Zero External Dependencies:** Built using Python standard library only (`xml.etree.ElementTree`, `json`, `argparse`, `pathlib`, `re`, `datetime`).
- **Surrogate Safe:** Automatically sanitizes lone surrogate code points (`\ud800`–`\udfff`) from voice transcripts to guarantee valid UTF-8 XML encoding.
- **Atomic File Writing:** Writes via `.partial` before atomic rename to prevent corrupted partial writes.
- **Hierarchical Outline:** Structures conversations logically into high-level summaries, actionable task checklists, and readable chronological dialogue.
