#!/usr/bin/env python3
"""
Generate a SHA‑256 manifest for a directory of raw audio chunk files.

The script walks the supplied input directory (optionally recursively),
computes the SHA‑256 hash of each file, and writes a JSON manifest
containing the relative file paths and their hashes.  The output file
is written atomically to avoid partial writes.

Usage:
    python audio_chunks_to_manifest.py --input-dir /path/to/chunks \
                                       --output-file /path/to/manifest.json

The resulting JSON has the following structure:

{
    "chunks": [
        {"path": "chunk1.wav", "sha256": "abcd1234..."},
        {"path": "subdir/chunk2.wav", "sha256": "efgh5678..."},
        ...
    ]
}
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Return the SHA‑256 hex digest of the given file."""
    hash_obj = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
    except OSError as exc:
        logger.error("Failed to read %s: %s", file_path, exc)
        raise
    return hash_obj.hexdigest()


def collect_chunks(
    input_dir: Path, recursive: bool = False
) -> List[Dict[str, str]]:
    """Return a list of dicts with relative path and SHA‑256 hash."""
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path {input_dir} is not a directory")

    glob_pattern = "**/*" if recursive else "*"
    files = sorted(
        [p for p in input_dir.glob(glob_pattern) if p.is_file()],
        key=lambda p: p.name,
    )

    if not files:
        logger.warning("No files found in %s", input_dir)

    chunks = []
    for file_path in files:
        rel_path = str(file_path.relative_to(input_dir))
        try:
            sha256 = compute_sha256(file_path)
        except Exception as exc:
            logger.error("Skipping %s due to error: %s", file_path, exc)
            continue
        chunks.append({"path": rel_path, "sha256": sha256})
        logger.debug("Processed %s", rel_path)

    return chunks


def write_manifest_atomic(output_path: Path, data: Dict) -> None:
    """Write JSON data to a temporary file and atomically replace the target."""
    temp_path = output_path.with_suffix(".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, sort_keys=True)
        temp_path.replace(output_path)
        logger.info("Manifest written to %s", output_path)
    except OSError as exc:
        logger.error("Failed to write manifest: %s", exc)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a SHA‑256 manifest for raw audio chunk files."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing raw audio chunk files.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        type=Path,
        help="Path to write the JSON manifest.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively walk subdirectories.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        chunks = collect_chunks(args.input_dir, args.recursive)
        manifest = {"chunks": chunks}
        write_manifest_atomic(args.output_file, manifest)
    except Exception as exc:
        logger.error("Failed to generate manifest: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
