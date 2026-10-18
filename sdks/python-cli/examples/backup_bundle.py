#!/usr/bin/env python3
"""Bundle Omi CLI JSON/text exports into a single verified .tar.gz backup.

See backup_bundle.md for the full recipe.

Usage:
    # Create a bundle with an embedded SHA-256 manifest
    python backup_bundle.py memories.json conversations.json action_items.json goals.json -o backup.tar.gz

    # Verify a bundle's integrity without extracting to disk
    python backup_bundle.py --verify backup.tar.gz

Every member is hashed (SHA-256) and measured (byte length) into an embedded
``manifest.json``; ``--verify`` re-reads the archive and re-checks every
member against it. Normalized mtime keeps bundles deterministic.
"""

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_NAME = "manifest.json"
EPOCH_MTIME = 946684800  # 2000-01-01T00:00:00Z — deterministic archive timestamps


def _entry_payload(name: str, data: bytes) -> tarfile.TarInfo:
    """Build a deterministic TarInfo for one in-memory member."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = EPOCH_MTIME
    info.mode = 0o644
    return info


def build(sources: List[str], destination: str) -> Dict[str, Any]:
    """Pack the source files + manifest into *destination*; return the manifest.

    Refuses '..' in the destination, refuses to overwrite an existing file,
    and refuses member names that would escape the archive root.
    """
    dest = Path(destination)
    if ".." in dest.parts:
        raise ValueError(f"Refusing '..' in output path {destination}")
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite existing {dest}")

    manifest: Dict[str, Any] = {"version": 1, "files": {}}
    members: List[tuple] = []
    seen = set()
    for src in sources:
        p = Path(src)
        name = p.name
        if name in seen or name == MANIFEST_NAME:
            raise ValueError(f"duplicate or reserved member name: {name}")
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"unsafe member name: {name}")
        seen.add(name)
        data = p.read_bytes()
        manifest["files"][name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        members.append((name, data))

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    members.append((MANIFEST_NAME, manifest_bytes))

    try:
        fd = dest.open("xb")
    except OSError as e:
        raise ValueError(f"cannot create {destination}: {e}") from e
    try:
        with fd:
            with tarfile.open(fileobj=fd, mode="w:gz") as tar:
                for name, data in members:
                    tar.addfile(_entry_payload(name, data), io.BytesIO(data))
    except OSError:
        dest.unlink(missing_ok=True)
        raise
    return manifest


def verify(bundle: str) -> Dict[str, Any]:
    """Re-check every member against the embedded manifest.

    Reads the archive entirely in memory — nothing is extracted to disk.
    Returns the manifest on success; raises ValueError on any mismatch,
    missing member, or corrupt archive.
    """
    try:
        with tarfile.open(bundle, mode="r:gz") as tar:
            names = set(tar.getnames())
            if MANIFEST_NAME not in names:
                raise ValueError(f"{bundle}: missing {MANIFEST_NAME}")
            manifest = json.loads(tar.extractfile(MANIFEST_NAME).read().decode("utf-8"))
            for name, expected in manifest.get("files", {}).items():
                if name not in names:
                    raise ValueError(f"{bundle}: missing member {name}")
                member = tar.extractfile(name)
                data = member.read()
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected["sha256"]:
                    raise ValueError(
                        f"{bundle}: {name} SHA-256 mismatch "
                        f"(expected {expected['sha256'][:16]}…, got {actual[:16]}…)"
                    )
                if len(data) != expected["size"]:
                    raise ValueError(f"{bundle}: {name} size mismatch")
            return manifest
    except tarfile.TarError as e:
        raise ValueError(f"{bundle}: not a readable tar.gz archive: {e}") from e


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Bundle Omi CLI exports into a verified .tar.gz backup, or verify one.")
    ap.add_argument("inputs", nargs="*", help="JSON/text export files to bundle")
    ap.add_argument("-o", "--output", help="Destination .tar.gz path (exclusive create)")
    ap.add_argument("--verify", metavar="BUNDLE", help="Verify an existing bundle without extracting")
    args = ap.parse_args(argv)

    if args.verify:
        try:
            manifest = verify(args.verify)
        except ValueError as e:
            print(f"backup_bundle: {e}", file=sys.stderr)
            return 2
        n = len(manifest.get("files", {}))
        print(f"backup_bundle: {args.verify} verified — {n} file(s) intact", file=sys.stderr)
        return 0

    if not args.inputs or not args.output:
        ap.error("inputs and -o/--output are required when not using --verify")
    try:
        manifest = build(args.inputs, args.output)
    except (ValueError, FileExistsError, OSError) as e:
        print(f"backup_bundle: {e}", file=sys.stderr)
        return 2
    print(
        f"backup_bundle: wrote {args.output} with {len(manifest['files'])} file(s) + manifest",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
