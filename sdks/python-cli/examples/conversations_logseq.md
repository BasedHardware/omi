# Convert conversations to a Logseq page

Use this recipe when you keep your notes in [Logseq](https://logseq.com) — it writes a single Logseq-native outliner page where each conversation is a block titled from its summary, tagged by category, with its overview as a nested child block. It reads a saved JSON export, makes no network requests, and complements [`conversations_markdown.md`](conversations_markdown.md) (which targets Obsidian/Notion specifically).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your conversations:

```sh
omi --json conversation list --limit 200 > conversations.json
```

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_logseq.py conversations.json conversations.md
```

Drop `conversations.md` into your Logseq graph's `pages/` directory and open it. Each block has `date::`/`omi-id::` properties and a `#category` hashtag (Logseq turns it into a linked page you can browse all conversations in that category from). Conversations without a processed `structured` summary yet still get a block ("Untitled conversation") instead of being silently skipped.

**Tag/link injection safety:** Logseq treats `#word` and `[[Page]]` as live syntax anywhere in a block's text — a title or overview containing `#something` or `[[something]]` would otherwise silently create an unintended tag or page link. This converter escapes every `[[`, `]]`, and `#` found in the title/overview before writing them. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
