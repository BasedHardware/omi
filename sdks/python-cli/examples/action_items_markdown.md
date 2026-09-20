# Export action items to a Markdown checklist (Obsidian Tasks / Notion)

Use this recipe to turn your Omi action items into a Markdown checklist you can
keep in an Obsidian vault, a Notion page or any notes app. Open items become
`- [ ]` lines and completed items `- [x]` lines, due dates use the
[Obsidian Tasks](https://publish.obsidian.md/tasks/) emoji format
(`📅 YYYY-MM-DD`) so the plugin can sort and query them, and every line keeps the
Omi item ID so you can find it again with `omi action-item get`. It reads saved
JSON exports, makes no network requests, and writes one Markdown file. You need
Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your action items (up to 500 per page; drop `--open` to include
completed ones):

```sh
omi --json action-item list --open --limit 500 --offset 0 > action_items_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 500 and use a different filename; the converter accepts several files and
keeps the last occurrence of each item ID.

Save the following as `action_items_to_markdown.py`:

```python
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def line_text(value):
    """Render a field as a single Markdown line; anything non-null is coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def utc_date(value):
    """Parse an ISO-8601 timestamp into a UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_items(sources):
    items = {}
    for source in sources:
        data = json.loads(Path(source).read_bytes())
        if not isinstance(data, list):
            raise ValueError(f"{source}: expected the JSON array from omi --json action-item list")
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each action item must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: each action item needs a string id")
            items[item_id] = item  # a later file wins, so re-exports update earlier pages
    return items


def task_line(item_id, item):
    box = "[x]" if item.get("completed") is True else "[ ]"
    description = line_text(item.get("description")) or "(no description)"
    parts = [f"- {box} {description}"]
    due = utc_date(item.get("due_at"))
    if due is not None:
        parts.append(f"📅 {due:%Y-%m-%d}")
    done = utc_date(item.get("completed_at"))
    if item.get("completed") is True and done is not None:
        parts.append(f"✅ {done:%Y-%m-%d}")
    parts.append(f"`omi:{item_id}`")
    return " ".join(parts)


def sort_key(entry):
    """Due-dated items first (earliest due first), then undated items by creation time."""
    item_id, item = entry
    due, created = utc_date(item.get("due_at")), utc_date(item.get("created_at"))
    far = datetime.max.replace(tzinfo=timezone.utc)
    return (due is None, due or far, created or far, item_id)


def render(items):
    open_items = sorted(((i, it) for i, it in items.items() if it.get("completed") is not True), key=sort_key)
    done_items = sorted(((i, it) for i, it in items.items() if it.get("completed") is True), key=sort_key)
    now = datetime.now(timezone.utc)
    lines = ["---", "source: omi-cli action-item list", f"exported_at: {now:%Y-%m-%dT%H:%M:%SZ}",
             f"open: {len(open_items)}", f"completed: {len(done_items)}", "---", "", "# Omi action items", "",
             f"## Open ({len(open_items)})", ""]
    lines += [task_line(i, it) for i, it in open_items] or ["_No open action items._"]
    lines += ["", f"## Completed ({len(done_items)})", ""]
    lines += [task_line(i, it) for i, it in done_items] or ["_No completed action items in this export._"]
    return "\n".join(lines) + "\n"


def convert(sources, destination):
    items = load_items(sources)
    payload = render(items).encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing note; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(items)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python action_items_to_markdown.py OUTPUT.md INPUT.json [INPUT.json ...]")
    try:
        count = convert(sys.argv[2:], sys.argv[1])
    except (OSError, ValueError) as exc:
        sys.exit(f"Markdown export failed: {exc}")
    print(f"{count} action item(s) written")
```

Run the converter (the output file comes first, then one or more exports):

```sh
python action_items_to_markdown.py "Omi Tasks.md" action_items_0.json
```

Drop the file into your vault or paste it into Notion. Each item is one line:
`- [ ] Send the budget draft 📅 2026-09-26 ` `` `omi:abc123` ``; completed items
use `- [x]` and add `✅ YYYY-MM-DD` when the export carries `completed_at`.
Open items are sorted by due date with undated ones last, so the top of the list
is what is due next. Dates are the UTC calendar date of the timestamp. Line
breaks inside a description are collapsed to spaces so every item stays on one
line, and the frontmatter records when the export was made and how many items
it holds. Re-running the converter on a fresh export refuses to overwrite the
existing note; delete or rename the old file first (Obsidian Tasks users can
also keep the exports as dated notes). The item ID at the end of each line is
what `omi action-item get`, `complete` and `update` expect. Treat the file as
private data.
