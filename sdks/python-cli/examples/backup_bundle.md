# Package Omi export files into a verifiable backup bundle (.tar.gz)

Use this recipe to aggregate multiple Omi data exports (`memories.json`, `conversations.json`,
`action_items.json`, `goals.json`) into a single compressed `.tar.gz` archive with an embedded
cryptographic SHA-256 manifest (`manifest.json`).

The script requires no third-party libraries, makes no network requests, and runs completely
offline using Python's standard library.

## Quickstart

### 1. Export your data with omi-cli

Export each dataset using the root `--json` flag:

```sh
omi --json memory list --limit 200 > memories.json
omi --json conversation list --limit 200 > conversations.json
omi --json action-item list --open --limit 200 > action_items.json
omi --json goal list --limit 100 --include-inactive > goals.json
```

### 2. Package into a backup bundle

Combine individual exported files into an archive:

```sh
python sdks/python-cli/examples/backup_bundle.py \
  memories.json conversations.json action_items.json goals.json \
  -o omi_backup.tar.gz
```

Or package an entire directory containing your exported files:

```sh
python sdks/python-cli/examples/backup_bundle.py ./my_omi_export/ -o omi_backup.tar.gz
```

Use `-f` or `--force` to overwrite an existing bundle:

```sh
python sdks/python-cli/examples/backup_bundle.py ./my_omi_export/ -o omi_backup.tar.gz --force
```

### 3. Verify bundle integrity

Verify that the archive has not been tampered with and that all files match their SHA-256 digests
without extracting files to disk:

```sh
python sdks/python-cli/examples/backup_bundle.py --verify omi_backup.tar.gz
```

Output:
```text
VERIFIED: Archive 'omi_backup.tar.gz' is valid. 4 files verified successfully against manifest.
```

## Manifest format

Each archive includes an embedded `manifest.json` as the first entry:

```json
{
  "version": "1.0",
  "format": "omi-backup-bundle",
  "created_at": "2026-10-06T12:00:00+00:00",
  "files_count": 4,
  "files": [
    {
      "path": "action_items.json",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size_bytes": 1024
    },
    {
      "path": "conversations.json",
      "sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
      "size_bytes": 2048
    }
  ]
}
```

## Security and Invariants

- **Path traversal protection**: Rejects input and output paths containing `..` path segments.
- **Atomic file creation**: Writes to a temporary sibling file (`.tmp_bundle_*.tar.gz`) before replacing the destination via `os.replace`, ensuring failed or interrupted writes never leave corrupted bundles.
- **No-clobber default**: Refuses to overwrite existing files unless explicitly requested with `-f`/`--force`.
- **Pure standard library**: Uses only `argparse`, `hashlib`, `json`, `os`, `pathlib`, `sys`, `tarfile`, and `tempfile`.
