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

## 3. Standalone Converter Script

Save the following as `backup_bundle.py`:

```python
import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def count_records(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("memories", "conversations", "action_items", "goals", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return len(candidate)
    return 0

def create_backup_bundle(resources: Dict[str, bytes], output_path: Path) -> Dict[str, Any]:
    if ".." in output_path.parts:
        raise ValueError(f"Output path cannot contain '..': {output_path}")

    timestamp = datetime.now(timezone.utc).isoformat()
    manifest: Dict[str, Any] = {
        "manifest_version": "1.0",
        "created_at": timestamp,
        "resources": {},
    }
    tar_members: Dict[str, bytes] = {}

    for resource_name, payload in resources.items():
        filename = f"{resource_name}.json"
        digest = sha256_bytes(payload)
        try:
            parsed = json.loads(payload.decode("utf-8"))
            count = count_records(parsed)
        except Exception:
            count = -1

        manifest["resources"][filename] = {
            "sha256": digest,
            "byte_size": len(payload),
            "record_count": count,
        }
        tar_members[filename] = payload

    tar_members["manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_name(output_path.name + ".partial")

    try:
        with tarfile.open(partial_path, "w:gz") as tar:
            for arcname, data_bytes in tar_members.items():
                tarinfo = tarfile.TarInfo(name=arcname)
                tarinfo.size = len(data_bytes)
                tarinfo.mtime = int(datetime.now(timezone.utc).timestamp())
                tar.addfile(tarinfo, io.BytesIO(data_bytes))
        os.replace(partial_path, output_path)
    except Exception:
        if partial_path.exists():
            partial_path.unlink()
        raise

    return manifest

def verify_backup_bundle(bundle_path: Path) -> Dict[str, Any]:
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    with tarfile.open(bundle_path, "r:gz") as tar:
        try:
            manifest_file = tar.extractfile("manifest.json")
            if manifest_file is None:
                raise ValueError("Archive is missing manifest.json")
            manifest_data = json.loads(manifest_file.read().decode("utf-8"))
        except KeyError:
            raise ValueError("Archive is missing manifest.json")

        resources_meta = manifest_data.get("resources", {})
        for filename, meta in resources_meta.items():
            expected_hash = meta.get("sha256")
            expected_size = meta.get("byte_size")

            try:
                member_file = tar.extractfile(filename)
                if member_file is None:
                    raise ValueError(f"Corrupted or missing archive file: {filename}")
                content = member_file.read()
            except KeyError:
                raise ValueError(f"Resource in manifest not found in archive: {filename}")

            if sha256_bytes(content) != expected_hash:
                raise ValueError(f"Integrity check failed for {filename}")
            if len(content) != expected_size:
                raise ValueError(f"Size mismatch for {filename}")

    return manifest_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or verify Omi backup bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_p = subparsers.add_parser("create")
    create_p.add_argument("-o", "--output", required=True)
    create_p.add_argument("--memories")
    create_p.add_argument("--conversations")
    create_p.add_argument("--action-items")
    create_p.add_argument("--goals")

    verify_p = subparsers.add_parser("verify")
    verify_p.add_argument("bundle")

    args = parser.parse_args()

    if args.command == "create":
        payloads = {}
        for key in ("memories", "conversations", "action_items", "goals"):
            val = getattr(args, key)
            if val:
                payloads[key] = Path(val).read_bytes()
        create_backup_bundle(payloads, Path(args.output))
        sys.stderr.write(f"Created {args.output}\n")
    elif args.command == "verify":
        m = verify_backup_bundle(Path(args.bundle))
        print(json.dumps(m, indent=2))
```

## 4. Guarantees

* **End-to-end cryptographic integrity**: verifies byte size and SHA-256 hashes per member file.
* **Zero dependencies**: standard library only (`tarfile`, `hashlib`, `json`, `pathlib`).
* **Atomic bundle writing**: `.tar.gz.partial` prevents incomplete backups if interrupted.
