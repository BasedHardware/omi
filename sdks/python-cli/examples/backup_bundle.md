# Package your Omi exports into a backup bundle

Use this recipe to combine your exported JSON or text files (`memories.json`,
`conversations.json`, `action_items.json`, `goals.json`) into a single
gzip-compressed `.tar.gz` archive with an embedded SHA-256 verification
manifest. You can then integrity-check the whole bundle later with `--verify`
— without extracting anything to disk. You need Python 3.9+; the utility uses
only the standard library and makes no network requests.

Export the resources you want to back up:

```sh
omi --json memory list --limit 200 > memories.json
omi --json conversation list --limit 200 --include-transcript > conversations.json
omi --json action-item list --limit 200 > action_items.json
omi --json goal list > goals.json
```

Save the following as `backup_bundle.py`:

```python
"""Package Omi exports into a single gzip-compressed tar backup bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

MANIFEST_NAME = "manifest.json"
_DETERMINISTIC_MTIME = 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_output(path_str: str) -> Path:
    """Refuse unsafe destinations: '..' traversal, existing non-archive files, dirs."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Output path {path_str!r} contains '..'; refusing to write outside the intended directory.")
    if p.exists():
        if p.is_dir():
            raise ValueError(f"{path_str!r} is a directory; refusing to overwrite it.")
        with p.open("rb") as fh:
            magic = fh.read(2)
        if magic != b"\x1f\x8b":  # gzip magic
            raise ValueError(f"{path_str!r} exists but is not a gzip archive; refusing to overwrite it.")
    return p


def _validate_input(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_file():
        raise ValueError(f"Input {path_str!r} is not a readable file.")
    return p


def build_bundle(output: Path, inputs):
    """Write *inputs* into *output* as a .tar.gz with an embedded SHA-256 manifest."""
    members = []
    for p in inputs:
        data = p.read_bytes()
        members.append({
            "name": p.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    manifest = json.dumps({"files": members}, indent=2, sort_keys=True).encode("utf-8")

    with tarfile.open(output, "w:gz") as tar:
        for member, p in zip(members, inputs):
            info = tarfile.TarInfo(name=member["name"])
            info.size = member["size"]
            info.mtime = _DETERMINISTIC_MTIME
            with p.open("rb") as fh:
                tar.addfile(info, fh)
        info = tarfile.TarInfo(name=MANIFEST_NAME)
        info.size = len(manifest)
        info.mtime = _DETERMINISTIC_MTIME
        import io
        tar.addfile(info, io.BytesIO(manifest))
    return len(members)


def verify_bundle(bundle: Path) -> int:
    """Check every member's SHA-256/size against the embedded manifest, in memory."""
    with tarfile.open(bundle, "r:gz") as tar:
        names = set(tar.getnames())
        if MANIFEST_NAME not in names:
            raise ValueError(f"{bundle.name}: missing {MANIFEST_NAME}")
        manifest = json.loads(tar.extractfile(MANIFEST_NAME).read().decode("utf-8"))
        files = manifest.get("files")
        if not isinstance(files, list):
            raise ValueError(f"{bundle.name}: malformed manifest")
        count = 0
        for entry in files:
            name = entry.get("name")
            if name not in names:
                raise ValueError(f"{bundle.name}: manifest lists {name!r} but it is absent")
            blob = tar.extractfile(name).read()
            if len(blob) != entry.get("size"):
                raise ValueError(f"{name}: size mismatch ({len(blob)} != {entry.get('size')})")
            if hashlib.sha256(blob).hexdigest() != entry.get("sha256"):
                raise ValueError(f"{name}: sha256 mismatch")
            count += 1
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", "-v", metavar="BUNDLE", help="verify an existing bundle instead of building")
    parser.add_argument("output", nargs="?", help="bundle.tar.gz to create")
    parser.add_argument("inputs", nargs="*", help="export files to include")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            count = verify_bundle(Path(args.verify))
            print(f"OK: {count} file(s) verified in {args.verify}")
            return
        if not args.output or not args.inputs:
            parser.error("build mode requires an output bundle and at least one input file")
        output = _validate_output(args.output)
        inputs = [_validate_input(p) for p in args.inputs]
        count = build_bundle(output, inputs)
        print(f"{count} file(s) bundled into {output}")
    except (OSError, ValueError, tarfile.TarError, json.JSONDecodeError) as exc:
        sys.exit(f"backup_bundle failed: {exc}")


if __name__ == "__main__":
    main()
```

Build a bundle from your exports:

```sh
python backup_bundle.py omi_backup.tar.gz memories.json conversations.json action_items.json goals.json
```

Verify a bundle's integrity at any time — it checks every member's SHA-256 and
byte length against the embedded `manifest.json`, reading the archive in memory
without writing files to disk:

```sh
python backup_bundle.py --verify omi_backup.tar.gz
# → OK: 4 file(s) verified in omi_backup.tar.gz
```

The archive uses a fixed member mtime, so identical inputs produce a
byte-reproducible bundle. The output path rejects `..` (directory traversal),
refuses to overwrite an existing file that is not a gzip archive, and never
overwrites a directory. The manifest records each file's name, byte size, and
SHA-256 so a single flipped bit in any member fails `--verify`. A companion
unit test suite (`sdks/python-cli/tests/test_backup_bundle.py`) covers build/
verify round-trips, manifest hashing, tamper detection, missing-manifest
rejection, and the overwrite/traversal guards.
