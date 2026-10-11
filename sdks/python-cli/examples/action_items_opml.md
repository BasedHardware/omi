# Omi Action Items to OPML

## Overview
This recipe extracts action items from your Omi device history and converts them into an OPML (Outline Processor Markup Language) 2.0 file. OPML is the standard format for outlining and is natively supported by outliners and task managers such as:
- OmniFocus
- Workflowy
- Dynalist
- Logseq
- MindNode
- Roam Research

## Quickstart

1. **Fetch action items from Omi CLI**:
   ```bash
   omi --json action-item list --limit 500 > action_items.json
   ```

2. **Convert to OPML**:
   ```bash
   python action_items_to_opml.py action_items.json omi_tasks.opml
   ```
   
   *Alternatively, pipe the JSON directly:*
   ```bash
   omi --json action-item list | python action_items_to_opml.py - omi_tasks.opml
   ```

## OPML Structure

The generated OPML maps Omi fields to standard outline attributes:
- `text`: The task description.
- `_status`: `completed` or `open` (mapped from Omi's completed status).
- `created`: The creation timestamp.
- `due`: The due date (mapped from `due_at`, `due_date`, or `due`).

Example output:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Omi Action Items</title>
    <dateCreated>2024-01-01T12:00:00+00:00</dateCreated>
  </head>
  <body>
    <outline text="Review Omi recordings" _status="open" created="2024-01-01T10:00:00Z" />
    <outline text="Send follow-up email" _status="completed" />
  </body>
</opml>
```

## App Import Guides

### Workflowy / Dynalist
1. Open your workspace.
2. Drag and drop the `omi_tasks.opml` file into a node, or use the **Import** menu and select OPML.
3. Tasks will populate with their descriptions as bullets.

### Logseq
1. Click on the three dots `...` in the top right corner.
2. Select **Import**, then choose **OPML**.
3. Logseq will convert the outlines into blocks.

### OmniFocus
1. Go to **File > Import...**
2. Select your `omi_tasks.opml` file.
3. OmniFocus will map the outline hierarchy to Action Items or Projects.