# Recipe: Export action items to HTML

Convert the JSON output of `omi action-item list` into a self-contained,
browser-ready HTML table — no external dependencies, no network access.

## Prerequisites

- Python 3.8 or later (stdlib only)
- Omi CLI authenticated: `omi auth login`

## Usage

```bash
# Pipe directly from the CLI
omi --json action-item list | python action_items_html.py

# Save the JSON first, then convert
omi --json action-item list > items.json
python action_items_html.py --input items.json --output action_items.html

# Overwrite an existing output file
python action_items_html.py --input items.json --overwrite
```

The script writes `action_items.html` (configurable via `--output`) and prints
a summary line, e.g. `Written 42 item(s) → action_items.html`.

## How it works

| Step | Detail |
|------|--------|
| Parse | Reads a JSON array or `{"items": […]}` wrapper from stdin or a file |
| Deduplicate | Drops items with the same `conversation_id` + `description` pair |
| Render | Builds an escaped, self-contained HTML table (no external CSS/JS) |
| Write | Opens the output file with mode `'x'` to prevent silent overwrites |

## Output

The generated page contains four columns:

| Column | Source field |
|--------|--------------|
| Task | `description` (falls back to `text` / `content`) |
| Conversation ID | `conversation_id` / `memory_id` |
| Created | `created_at` / `timestamp` |
| Status | `completed` / `done` / `status` |

## Options

```
-i FILE, --input FILE    JSON source file (default: stdin)
-o FILE, --output FILE   HTML destination (default: action_items.html)
--overwrite              Replace output file if it already exists
```

## Related recipes

See the [full example index](README.md) for more recipes (ICS calendar export,
todo.txt, CSV, xlsx, SQLite, Atom feed, Org-mode, Markdown, and others).
