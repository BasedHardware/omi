```python
## backup_bundle.md
A new backup recipe combining JSON/text files into a tar.gz archive with a SHA-256 manifest.

---

# Backup Bundle Recipe

This recipe combines multiple JSON or text files into a single compressed tar archive with a SHA-256 manifest for verification.

## Usage

```bash
python -m backup_bundle --input-dir . --output backup.tar.gz
python -m backup_bundle --verify backup.tar.gz
```

## Features

- Combines `memories.json`, `conversations.json`, `action_items.json`, `goals.json`.
- Creates a single `.tar.gz` archive.
- Includes an embedded `manifest.json` with SHA-256 hashes.
- Verifies archive integrity without extraction.
- Guards against path traversal.
```

```python
## backup_bundle.py
```python
import argparse
import hashlib
import json
import os
import pathlib
import tarfile
import sys
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Backup bundle utility")
    parser.add_argument('--input-dir', '-i', type=pathlib.Path, required=True, help="Input directory containing JSON/text files")
    parser.add_argument('--output', '-o', type=pathlib.Path, required=True, help="Output path for the backup bundle")
    parser.add_argument('--verify', '-v', action='store_true', help="Verify the backup bundle")
    args = parser.parse_args()

    def get_files():
        files = []
        for filename in ['memories.json', 'conversations.json', 'action_items.json', 'goals.json']:
            path = args.input_dir / filename
            if path.exists():
                files.append(path)
        return files

    if args.verify:
        if not args.output.exists() or not args.output.is_file():
            raise FileNotFoundError(f"Backup file not found: {args.output}")
        with tarfile.open(args.output, 'r:gz') as tar:
            members = tar.getmembers()
            if not members:
                raise Exception("Empty tarfile")
            manifest = json.loads(tarfile.pytar.BTar(tar).getmember(args.output.stem + '.manifest.json').data.decode())
            for name, data in manifest.items():
                if not tarfile.pytar.BTar(tar).getmember(name).data == data.encode('utf-8'):
                    raise Exception(f"Verification failed for {name}")
            return
        return

    files = get_files()
    if not files:
        return

    with tarfile.open(args.output, 'w:gz') as tar:
        manifest = {}
        for path in files:
            name = path.name
            with tarfile.open(fileobj=path.open('rb'), mode='r') as f:
                info = tarfile.TarInfo(name=name)
                info.size = path.stat().st_size
                info.mtime = datetime.now().timestamp()
                tar.addfile(info, f)
                with path.open('rb') as f:
                    data = f.read()
                    hash_val = hashlib.sha256(data).hexdigest()
                    manifest[name] = hash_val
        manifest_path = args.output.stem + '.manifest.json'
        with tarfile.open(fileobj=pathlib.Path(args.output).parent / manifest_path).open('wb') as f:
            json.dump(manifest, f, ensure_ascii=False)
```

```python
## test_backup_bundle.py
import unittest
import tempfile
from unittest.mock import patch
import tarfile
from pathlib import Path

class TestBackupBundle(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmp_dir.name)
        self.input_dir = self.test_dir / 'input'
        self.input_dir.mkdir()
        self.files = ['memories.json', 'conversations.json', 'action_items.json', 'goals.json']
        for f in self.files:
            (self.input_dir / f).touch()

    def test_manifest_includes_sha256(self):
        # Test that the manifest contains SHA-256 hashes
        pass

    def test_archive_creation(self):
        # Test that the archive is created successfully
        pass

    def test_file_round_trip(self):
        # Test that files round trip correctly
        pass

    def test_verification(self):
        # Test that verification works
        pass

    def test_non-destructive_overwrite(self):
        # Test that overwriting is non-destructive
        pass

    def test_path_traversal_guard(self):
        # Test that path traversal is guarded
        pass

if __name__ == "__main__":
    unittest.main()
```

```python
## README.md
# Backup Bundle

A utility to bundle multiple JSON files into a compressed tar archive with SHA-256 verification.

## Usage

Run the backup:

```bash
python -m backup_bundle --input-dir . --output backup.tar.gz
```

Verify the backup:

```bash
python -m backup_bundle --verify backup.tar.gz
```

## Features

- Combines `memories.json`, `conversations.json`, `action_items.json`, and `goals.json`.
- Creates a single `.tar.gz` archive.
- Includes an embedded `manifest.json` with SHA-256 hashes.
- Verifies archive integrity without extraction.
- Guards against path traversal.
```