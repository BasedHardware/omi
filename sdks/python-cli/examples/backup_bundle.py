"""Package Omi exports into a single gzip-compressed tar backup bundle.

Builds a ``.tar.gz`` containing the given export files plus an embedded
``manifest.json`` with a SHA-256 hash and byte length for every member, so the
bundle can be integrity-checked later without extracting it.

Usage:
    python backup_bundle.py bundle.tar.gz memories.json conversations.json
    python backup_bundle.py --verify bundle.tar.gz

Only the Python standard library is used (argparse, hashlib, json, os, pathlib,
sys, tarfile). Compatible with Python 3.9+ and fully offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

MANIFEST_NAME = "manifest.json"
# A fixed mtime makes the archive byte-reproducible for identical inputs.
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
