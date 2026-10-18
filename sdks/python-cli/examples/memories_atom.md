# Publish memories as an Atom feed

Use this recipe so a feed reader — NetNewsWire, Thunderbird, Feedly's local
import — can flag new memories as Omi saves them. It reads saved JSON
exports, makes no network requests, and writes one Atom 1.0 `.xml` file.
Stdlib only. You need Python 3.9+ and an authenticated `omi-cli` for the
initial export.

Export your memories:

```sh
omi --json memory list > memories.json
```

## The converter

The script lives at [`memories_to_atom.py`](memories_to_atom.py) in this
directory — same shape as the `conversations_to_atom` recipe.

**Privacy-first:** the entry `<summary>` carries metadata only — category,
visibility, tags, capture time — **never the memory's content text**. A
memory can hold private material; the feed flags *that* a memory exists and
*when*, not what it says. (The `<title>` does carry a truncated first line —
drop the feed only into readers you trust.)

```xml
<entry>
  <title>Loves espresso &amp; hates meetings</title>
  <id>urn:omi:memory:m1</id>
  <updated>2026-10-17T14:00:00Z</updated>
  <published>2026-10-17T10:00:00Z</published>
  <category term="personal"/>
  <summary type="text">Category: personal - Visibility: public - Tags: coffee, work - Captured: 2026-10-17T10:00:00Z</summary>
</entry>
```

* One entry per memory, **newest first**; `created_at` drives `published`
  and `updated` (UTC RFC 3339).
* Control characters, lone surrogates, and XML non-characters are dropped —
  an unusual memory still parses.
* Multi-file dedupe: each memory ID appears once.

## Usage

```sh
python memories_to_atom.py memories.xml memories.json [memories2.json ...]
```

Then point your reader at `memories.xml` (import or file:// subscription).

## Input tolerance

Unwraps `{"memories": [...]}`, `{"items": ...}`, `{"data": ...}`, a bare
array, or a single object; accepts UTF-8 BOM input.

## Safety

* `..` in the output path is refused.
* Exclusive `xb` create — never overwrites; a failed write leaves no partial
  file.
* Malformed JSON or a missing input exits `2`.
