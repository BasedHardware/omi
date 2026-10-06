# Backup Bundle Recipe

This recipe shows how to combine your exported Omi data files into a single gzip-compressed tar archive with embedded SHA-256 verification.

## What it bundles

The archive packages these exported files together:
- `memories.json`
- `conversations.json`
- `action_items.json`
- `goals.json`

## Create the bundle

Run the helper script from this directory:

```bash
python backup_bundle.py ./my_omi_export/ -o omi_backup.tar.gz
```

This produces a deterministic tarball with normalized timestamps.

## Verify the bundle

Check archive integrity without extracting files:

```bash
python backup_bundle.py --verify omi_backup.tar.gz
```

## Security

The archive includes a `manifest.json` with SHA-256 hashes and byte lengths for every included file. Path traversal attacks (`..` in filenames) are rejected automatically.
