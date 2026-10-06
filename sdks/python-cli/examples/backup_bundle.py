#!/usr/bin/env python3
"""
Package Omi exported data files into a verifiable, compressed backup bundle.

Usage:
    python backup_bundle.py input_file1.json [input_file2.json ...] -o omi_backup.tar.gz
    python backup_bundle.py ./export_dir/ -o omi_backup.tar.gz
    python backup_bundle.py --verify omi_backup.tar.gz

Combines exported JSON or text files (memories, conversations, action items,
goals) into a single gzip-compressed tar archive (.tar.gz) containing an
embedded SHA-256 cryptographic verification manifest (manifest.json).

Zero external dependencies: uses only Python standard library.
"""

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def compute_sha256(data: bytes) -> str:
    """Calculate the SHA-256 hex digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def validate_path_safety(path: Path) -> None:
    """Ensure path does not contain directory traversal components ('..')."""
    for part in path.parts:
        if part == "..":
            raise ValueError(f"Path traversal ('..') is not permitted: {path}")


def collect_input_files(inputs: List[str]) -> List[Tuple[str, bytes]]:
    """
    Collect and read input files from file paths or directories.
    Returns a sorted list of (archive_arcname, content_bytes).
    """
    files_to_pack: Dict[str, bytes] = {}

    for item in inputs:
        p = Path(item)
        if not p.exists():
            raise FileNotFoundError(f"Input path not found: {item}")

        validate_path_safety(p)

        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    validate_path_safety(child)
                    rel_name = child.relative_to(p).as_posix()
                    if rel_name not in files_to_pack:
                        files_to_pack[rel_name] = child.read_bytes()
        elif p.is_file():
            arcname = p.name
            if arcname not in files_to_pack:
                files_to_pack[arcname] = p.read_bytes()

    if not files_to_pack:
        raise ValueError("No files found to bundle into archive.")

    return sorted(files_to_pack.items(), key=lambda x: x[0])


def build_bundle(
    inputs: List[str],
    output_path: Path,
    force: bool = False,
    deterministic_mtime: int = 1700000000,
) -> Path:
    """
    Pack collected files into a .tar.gz bundle with an embedded manifest.json.
    Writes atomically via a temporary sibling file and guards against clobbering.
    """
    validate_path_safety(output_path)

    if output_path.exists() and not force:
        raise FileExistsError(
            f"Destination '{output_path}' already exists. Use -f/--force to overwrite."
        )

    file_entries = collect_input_files(inputs)

    manifest_files = []
    for arcname, data in file_entries:
        manifest_files.append({
            "path": arcname,
            "sha256": compute_sha256(data),
            "size_bytes": len(data),
        })

    created_iso = datetime.now(timezone.utc).isoformat()
    manifest_doc = {
        "version": "1.0",
        "format": "omi-backup-bundle",
        "created_at": created_iso,
        "files_count": len(file_entries),
        "files": manifest_files,
    }
    manifest_bytes = json.dumps(manifest_doc, indent=2, ensure_ascii=False).encode("utf-8")

    out_dir = output_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write to temporary file in same directory
    temp_fd, temp_path_str = tempfile.mkstemp(
        prefix=".tmp_bundle_", suffix=".tar.gz", dir=str(out_dir)
    )
    os.close(temp_fd)
    temp_path = Path(temp_path_str)

    try:
        with tarfile.open(temp_path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            # 1. Add manifest.json as the first entry
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            manifest_info.mtime = deterministic_mtime
            manifest_info.mode = 0o644
            manifest_info.type = tarfile.REGTYPE
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

            # 2. Add each file entry
            for arcname, data in file_entries:
                tar_info = tarfile.TarInfo(name=arcname)
                tar_info.size = len(data)
                tar_info.mtime = deterministic_mtime
                tar_info.mode = 0o644
                tar_info.type = tarfile.REGTYPE
                tar.addfile(tar_info, io.BytesIO(data))

        # Atomic replacement
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    return output_path


def verify_bundle(bundle_path: Path) -> Dict[str, object]:
    """
    Verify archive integrity against embedded manifest.json without extracting files to disk.
    Raises ValueError or tarfile.TarError if corrupted or tampered.
    """
    validate_path_safety(bundle_path)

    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    with tarfile.open(bundle_path, "r:gz") as tar:
        manifest_member = None
        try:
            manifest_member = tar.getmember("manifest.json")
        except KeyError:
            raise ValueError("Corrupt bundle: missing embedded 'manifest.json' manifest.")

        f = tar.extractfile(manifest_member)
        if f is None:
            raise ValueError("Failed to extract 'manifest.json' from archive.")
        manifest_raw = f.read()

        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Corrupt manifest.json: invalid JSON ({e})")

        expected_files = {item["path"]: item for item in manifest.get("files", [])}

        verified_count = 0
        for member in tar.getmembers():
            validate_path_safety(Path(member.name))
            if member.name == "manifest.json":
                continue

            if member.name not in expected_files:
                raise ValueError(
                    f"Integrity check failed: member '{member.name}' not found in manifest.json."
                )

            expected_meta = expected_files[member.name]
            ef = tar.extractfile(member)
            if ef is None:
                raise ValueError(f"Failed to read archive member '{member.name}'.")
            data = ef.read()

            if len(data) != expected_meta["size_bytes"]:
                raise ValueError(
                    f"Integrity check failed for '{member.name}': size mismatch "
                    f"({len(data)} != {expected_meta['size_bytes']})."
                )

            actual_sha = compute_sha256(data)
            if actual_sha != expected_meta["sha256"]:
                raise ValueError(
                    f"Integrity check failed for '{member.name}': SHA-256 hash mismatch "
                    f"({actual_sha} != {expected_meta['sha256']})."
                )

            verified_count += 1

        if verified_count != len(expected_files):
            raise ValueError(
                f"Integrity check failed: manifest contains {len(expected_files)} files, "
                f"but archive contains {verified_count} verified members."
            )

    return {
        "verified": True,
        "files_verified": verified_count,
        "created_at": manifest.get("created_at"),
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package Omi exported files into a verified gzip tar backup bundle."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input files or directories to include in the backup bundle.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output destination path for the backup archive (e.g. omi_backup.tar.gz).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing destination archive without confirmation.",
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="BUNDLE_FILE",
        help="Verify the integrity and SHA-256 hashes of an existing backup bundle without extracting.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.verify:
        bundle_path = Path(args.verify)
        try:
            result = verify_bundle(bundle_path)
            print(
                f"VERIFIED: Archive '{bundle_path.name}' is valid. "
                f"{result['files_verified']} files verified successfully against manifest."
            )
            return 0
        except Exception as exc:
            sys.stderr.write(f"Verification failed: {exc}\n")
            return 1

    if not args.inputs:
        sys.stderr.write("Error: missing input files or directories to bundle.\n")
        return 1

    if not args.output:
        sys.stderr.write("Error: -o/--output path is required when creating a bundle.\n")
        return 1

    out_path = Path(args.output)
    try:
        created = build_bundle(args.inputs, out_path, force=args.force)
        print(f"Created backup bundle: {created}")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error creating bundle: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
