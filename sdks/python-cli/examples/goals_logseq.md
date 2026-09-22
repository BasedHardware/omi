# Convert goals to a Logseq page

Use this recipe when you track goals inside [Logseq](https://logseq.com) — it writes a single Logseq-native outliner page where each goal is a block with `progress::`/`current::`/`target::` properties and an `#active`/`#completed` hashtag, so Logseq's linked-references view groups them by status automatically. It reads a saved JSON export and makes no network requests.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your tracked goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Run the converter:

```sh
python sdks/python-cli/examples/goals_to_logseq.py goals.json goals.md
```

Drop `goals.md` into your Logseq graph's `pages/` directory and open it. `progress::` is computed from `current_value / target_value`, falling back to the `min_value`–`max_value` range when `target_value` isn't usable.

**Tag/link injection safety:** Logseq treats `#word` and `[[Page]]` as live syntax anywhere in a block's text — a goal title containing `#something` or `[[something]]` would otherwise silently create an unintended tag or page link. This converter escapes every `[[`, `]]`, and `#` found in the title before writing it. The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
