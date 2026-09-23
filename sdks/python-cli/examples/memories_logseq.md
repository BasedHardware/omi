# Convert memories to a Logseq page

Use this recipe when your second brain is [Logseq](https://logseq.com), not Obsidian or Notion — it writes a single Logseq-native outliner page instead of one-file-per-note with YAML frontmatter. Each memory becomes a top-level block, tagged with its category and tags as real Logseq hashtags (`#work`, `#deep-work`) that Logseq turns into linked pages you can browse. It reads a saved JSON export, makes no network requests, and complements [`memories_markdown.md`](memories_markdown.md) (which targets Obsidian/Notion specifically).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your memories:

```sh
omi --json memory list --limit 200 > memories.json
```

Run the converter:

```sh
python sdks/python-cli/examples/memories_to_logseq.py memories.json memories.md
```

Drop `memories.md` into your Logseq graph's `pages/` (or `journals/`) directory and open it — each memory is a block with `created::` and `omi-id::` properties, tagged by category/tags for Logseq's built-in linked-references view.

**Tag/link injection safety:** Logseq treats `#word` and `[[Page]]` as live syntax anywhere in a block's text, not just at the start — so a memory whose content happens to contain `#something` or `[[something]]` would otherwise silently create an unintended tag or page link. This converter escapes every `[[`, `]]`, and `#` found in memory content before writing it, so only the hashtags the script itself generates from `category`/`tags` become real Logseq tags. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
