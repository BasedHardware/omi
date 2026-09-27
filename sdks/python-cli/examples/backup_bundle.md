# Bundle & verify multi-resource backups with SHA-256 manifests

Use this recipe to aggregate multiple Omi data exports (memories, conversations, action items, goals) into a single compressed `.tar.gz` archive with an embedded cryptographic manifest.

The embedded `manifest.json` tracks SHA-256 digests, payload sizes, and record tallies, allowing automated validation (`--verify`) to ensure archives are complete, uncorrupted, and tamper-free before archiving to cold storage or transferring between systems.

## 1. Create a compressed backup bundle

Bundle all exports into an integrity-verified tarball:

```sh
python backup_bundle.py create --output omi_backup_2026.tar.gz \
    --memories memories.json \
    --conversations conversations.json \
    --action-items action_items.json \
    --goals goals.json
```

## 2. Verify archive integrity

Validate the archive against its embedded cryptographic manifest:

```sh
python backup_bundle.py verify omi_backup_2026.tar.gz
```

Output:
```json
{
  "manifest_version": "1.0",
  "created_at": "2026-03-26T23:00:00.000000+00:00",
  "resources": {
    "memories.json": {
      "sha256": "573a7e186126e17226372ed2c39a946dc5e767cf7d711122af8eb9b239969e59",
      "byte_size": 204850,
      "record_count": 420
    },
    "conversations.json": {
      "sha256": "a3b984...",
      "byte_size": 512000,
      "record_count": 85
    }
  }
}
Verification successful: omi_backup_2026.tar.gz integrity confirmed.
```

## 3. Script Location

The complete, tested CLI utility is maintained at [`examples/backup_bundle.py`](./backup_bundle.py).

To execute directly:
```sh
python examples/backup_bundle.py create --output omi_backup.tar.gz --memories memories.json
python examples/backup_bundle.py verify omi_backup.tar.gz
```

## 4. Guarantees

* **End-to-end cryptographic integrity**: verifies byte size and SHA-256 hashes per member file.
* **Zero dependencies**: standard library only (`tarfile`, `hashlib`, `json`, `pathlib`).
* **Atomic bundle writing**: `.tar.gz.partial` prevents incomplete backups if interrupted.
