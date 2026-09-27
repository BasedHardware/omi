#!/usr/bin/env python3
"""
Bundle and verify Omi data exports into a single compressed, integrity-verified archive.

Usage:
    # Create archive with auto-manifest
    python backup_bundle.py create --output omi_backup.tar.gz \
        --memories memories.json \
        --conversations conversations.json \
        --action-items action_items.json \
        --goals goals.json

    # Verify existing archive integrity and manifest
    python backup_bundle.py verify omi_backup.tar.gz

Packages multiple Omi resource exports into a compressed tarball with SHA-256
checksums and record manifests for cold storage and migration.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def sha256_bytes(data: bytes) -> str:
    """Compute hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def count_records(data: Any) -> int:
    """Extract item count from bare array or envelope dict."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("memories", "conversations", "action_items", "goals", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return len(candidate)
    return 0


def create_backup_bundle(
    resources: Dict[str, bytes],
    output_path: Path,
) -> Dict[str, Any]:
    """Create a compressed .tar.gz bundle with embedded manifest and atomic write safety."""
    if ".." in output_path.parts:
        raise ValueError(f"Output path cannot contain directory traversal '..': {output_path}")

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

        # Parse record count
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

    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    tar_members["manifest.json"] = manifest_bytes

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
    """Verify integrity of tarball against embedded manifest."""
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    with tarfile.open(bundle_path, "r:gz") as tar:
        # Check manifest presence
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

            actual_hash = sha256_bytes(content)
            actual_size = len(content)

            if actual_hash != expected_hash:
                raise ValueError(
                    f"Integrity check failed for {filename}: expected {expected_hash}, got {actual_hash}"
                )
            if actual_size != expected_size:
                raise ValueError(
                    f"Size mismatch for {filename}: expected {expected_size} bytes, got {actual_size}"
                )

    return manifest_data


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify Omi backup bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a compressed backup bundle.")
    create_parser.add_argument("-o", "--output", required=True, help="Destination .tar.gz path.")
    create_parser.add_argument("--memories", help="Path to memories JSON.")
    create_parser.add_argument("--conversations", help="Path to conversations JSON.")
    create_parser.add_argument("--action-items", help="Path to action items JSON.")
    create_parser.add_argument("--goals", help="Path to goals JSON.")

    verify_parser = subparsers.add_parser("verify", help="Verify integrity of an existing bundle.")
    verify_parser.add_argument("bundle", help="Path to .tar.gz bundle to verify.")

    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            payloads: Dict[str, bytes] = {}
            if args.memories:
                payloads["memories"] = Path(args.memories).read_bytes()
            if args.conversations:
                payloads["conversations"] = Path(args.conversations).read_bytes()
            if args.action_items:
                payloads["action_items"] = Path(args.action_items).read_bytes()
            if args.goals:
                payloads["goals"] = Path(args.goals).read_bytes()

            if not payloads:
                sys.stderr.write("Error: At least one resource must be provided to create a bundle.\n")
                return 1

            out_path = Path(args.output)
            manifest = create_backup_bundle(payloads, out_path)
            sys.stderr.write(f"Successfully created bundle {out_path} with {len(payloads)} resources.\n")
            return 0

        elif args.command == "verify":
            manifest = verify_backup_bundle(Path(args.bundle))
            print(json.dumps(manifest, indent=2))
            sys.stderr.write(f"Verification successful: {args.bundle} integrity confirmed.\n")
            return 0

        return 0
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
