# Convert a conversation-list export to TSV

Use this recipe when the next step is shell text processing — `grep`,
`awk`, `cut`, `sed`. It reads a saved JSON export, makes no network
requests, and emits exactly **one line per record**: embedded newlines,
tabs, and carriage returns are escaped as `\n`, `\t`, `\r` so a multi-line
summary can never straddle two lines. You need Python 3.9+ and an
authenticated `omi-cli` for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one
page, not a complete-account backup. To retrieve another page, increase
`--offset` by 200 and use a different filename. Changes to the account
between requests can affect offset pagination; this recipe does not promise
a consistent snapshot.

## The converter

The script lives at [`conversations_to_tsv.py`](conversations_to_tsv.py) in
this directory — stdlib-only, zero external dependencies, works on Python
3.9 through 3.13+.

Columns: `id`, `title`, `category`, `started_at`, `finished_at`, `source`,
`overview`, `action_items_count`.

## Usage

Convert a saved export to a file:

```sh
python conversations_to_tsv.py conversations.json -o conversations.tsv
```

Stream straight to stdout for the classic pipeline:

```sh
omi --json conversation list --limit 200 | python conversations_to_tsv.py | cut -f3 | sort | uniq -c | sort -rn
```

```sh
python conversations_to_tsv.py conversations.json | grep -i 'meeting' | wc -l
```

## Input tolerance

The reader unwraps `{"conversations": [...]}`, `{"items": ...}`,
`{"data": ...}`, `{"results": ...}`, a bare array, or a single object;
accepts UTF-8 BOM input; treats error payloads as an empty export.

## Safety

* `..` in an `-o` destination path is refused.
* Malformed JSON or a missing input file exits `2` with a clean stderr
  message — no traceback.
* Non-dict records are dropped; one odd row cannot kill the export.
