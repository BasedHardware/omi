# Pack CLI exports into a verified backup bundle

Use this recipe to combine exported JSON or text files — `memories.json`,
`conversations.json`, `action_items.json`, `goals.json` — into a single
`.tar.gz` archive with an embedded SHA-256 verification manifest. It works
entirely offline, uses only the Python standard library, and never makes a
network request. You need Python 3.9+ and an authenticated `omi-cli` for the
initial exports.

Export the files you want to back up:

```sh
omi --json memory list > memories.json
omi --json conversation list --limit 200 > conversations.json
omi --json action-item list --limit 500 > action_items.json
omi --json goal list > goals.json
```

Check that each command succeeded before bundling.

## The bundler

The script lives at [`backup_bundle.py`](backup_bundle.py) in this directory —
stdlib-only (`tarfile`, `hashlib`, `json`, `pathlib`, `argparse`).

Every member is hashed (SHA-256) and measured (byte length) into an embedded
`manifest.json`; `--verify` re-reads the archive and re-checks every member
against it — nothing is extracted to disk. Member mtimes normalize to a fixed
epoch so two builds of identical inputs produce identical archives.

## Usage

Create a bundle:

```sh
python backup_bundle.py memories.json conversations.json action_items.json goals.json -o backup.tar.gz
```

Verify a bundle's integrity later (in-archive, no extraction):

```sh
python backup_bundle.py --verify backup.tar.gz
# → "backup_bundle: backup.tar.gz verified — 4 file(s) intact"
```

## Manifest

Each bundle embeds `manifest.json`:

```json
{
  "version": 1,
  "files": {
    "memories.json":      {"sha256": "…", "size": 12345},
    "conversations.json": {"sha256": "…", "size": 67890}
  }
}
```

`--verify` fails with a clean `SHA-256 mismatch` / `missing member` message if
any member is tampered with or removed.

## Safety

* `..` in the `-o` path is refused.
* Exclusive `xb` creation — an existing file is never overwritten; a failed
  write leaves no partial file.
* A member named `manifest.json` or a path-like member name is rejected — the
  manifest slot is reserved.
* Exit code `2` signals any failure.
