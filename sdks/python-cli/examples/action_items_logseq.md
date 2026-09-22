# Convert action items to a Logseq page (native task markers)

Use this recipe when your task tracking lives in [Logseq](https://logseq.com) — it writes a single Logseq-native outliner page where every action item is a real, checkable Logseq task block, not a GFM checkbox in a plain Markdown file. It reads a saved JSON export, makes no network requests, and complements [`action_items_markdown.md`](action_items_markdown.md) (which targets Obsidian/Notion specifically). See below for the exact markers used.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your action items:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Run the converter:

```sh
python sdks/python-cli/examples/action_items_to_logseq.py action_items.json action_items.md
```

Drop `action_items.md` into your Logseq graph's `pages/` directory and open it. Open items render as `TODO` (clickable to `DOING`/`DONE`); completed items are written as `DONE` directly. An open item with a `due_at` gets a Logseq `DEADLINE:` marker, so it shows up on your Logseq calendar/agenda view — completed items don't (there's nothing left to be reminded about).

**Tag/link injection safety:** Logseq treats `#word` and `[[Page]]` as live syntax anywhere in a block's text, not just at the start — so a description containing `#something` or `[[something]]` would otherwise silently create an unintended tag or page link. This converter escapes every `[[`, `]]`, and `#` found in the description before writing it. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
