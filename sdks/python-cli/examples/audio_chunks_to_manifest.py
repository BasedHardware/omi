#!/usr/bin/env python3
"""
audio_chunks_to_manifest.py

Recursively walks a directory containing raw audio chunk files and produces a
JSON manifest that maps each file (relative to the input directory) to its
SHA‑256 hash and size in bytes.

The manifest is written atomically – a temporary file is created in the same
directory as the target manifest and then renamed into place.

Typical usage::

    $ python -m sdks.python_cli.examples.audio_chunks_to_manifest \
        --input-dir ./audio_chunks \
        --output ./audio_chunks/manifest.json

The generated JSON has the following structure::

{
    "version": 1,
    "generated_at": "2026-09-22T12:34:56Z",
    "files": {
        "chunk001.wav": {
            "sha256": "3a7bd3e2360a...",
            "size": 123456
        },
        "subdir/chunk002.wav": {
            "sha256": "9c1e5f8b...",
            "size": 98765
        }
    }
}
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import pathlib
import shutil
import sys
import tempfile
from hashlib import sha256
from typing import Dict, Mapping

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
log = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)s: %(message)s")
handler.setFormatter(formatter)
log.addHandler(handler)
log.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #
def compute_sha256(file_path: pathlib.Path, chunk_size: int = 8192) -> str:
    """
    Compute the SHA‑256 hash of a file.

    Parameters
    ----------
    file_path: pathlib.Path
        Path to the file.
    chunk_size: int, optional
        Number of bytes to read per iteration (default 8192).

    Returns
    -------
    str
        Hex‑encoded SHA‑256 digest.
    """
    h = sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
    except OSError as exc:
        log.error("Failed to read %s: %s", file_path, exc)
        raise
    return h.hexdigest()


def index_directory(root_dir: pathlib.Path) -> Dict[str, Mapping[str, int | str]]:
    """
    Walk ``root_dir`` and build a manifest dictionary.

    Only regular files are indexed; directories themselves are ignored.
    The keys of the returned dict are POSIX‑style relative paths.

    Parameters
    ----------
    root_dir: pathlib.Path
        Directory to walk.

    Returns
    -------
    dict
        Mapping of relative path → {\"sha256\": ..., \"size\": ...}
    """
    if not root_dir.is_dir():
        raise NotADirectoryError(f"{root_dir} is not a directory")

    manifest: Dict[str, Mapping[str, int | str]] = {}
    for path in root_dir.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root_dir).as_posix()
        try:
            file_hash = compute_sha256(path)
            file_size = path.stat().st_size
            manifest[rel_path] = {"sha256": file_hash, "size": file_size}
            log.debug("Indexed %s → %s (%d bytes)", rel_path, file_hash, file_size)
        except Exception:
            # The error has already been logged in compute_sha256.
            # Abort the whole operation – a manifest must be complete.
            raise RuntimeError(f"Failed to process {path}") from None
    return manifest


def write_manifest_atomic(
    manifest: Mapping[str, Mapping[str, int | str]],
    output_path: pathlib.Path,
) -> None:
    """
    Write ``manifest`` to ``output_path`` atomically.

    The function creates a temporary file in the same directory as
    ``output_path`` and then renames it over the target file.

    Parameters
    ----------
    manifest: Mapping
        The manifest data to serialize.
    output_path: pathlib.Path
        Destination file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare the full JSON payload
    payload = {
        "version": 1,
        "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "files": manifest,
    }

    # Write to a temporary file first
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(output_path.parent),
        suffix=".tmp",
    ) as tmp_file:
        json.dump(payload, tmp_file, indent=2, sort_keys=True)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        temp_name = pathlib.Path(tmp_file.name)

    # Atomic replace
    try:
        os.replace(str(temp_name), str(output_path))
        log.info("Manifest written atomically to %s", output_path)
    finally:
        # In case replace failed, ensure the temp file is removed
        if temp_name.exists():
            temp_name.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index a directory of raw audio chunks into a SHA‑256 manifest."
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=pathlib.Path,
        required=True,
        help="Root directory containing audio chunk files.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to write the manifest JSON. If omitted, a file named "
            "'audio_chunks_manifest.json' will be created inside the input directory."
        ),
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational log messages; only errors are shown.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.ERROR)

    input_dir: pathlib.Path = args.input_dir.resolve()
    output_path: pathlib.Path = (
        args.output.resolve()
        if args.output
        else input_dir / "audio_chunks_manifest.json"
    )

    log.info("Indexing audio chunks in %s", input_dir)
    try:
        manifest = index_directory(input_dir)
        write_manifest_atomic(manifest, output_path)
    except Exception as exc:  # pragma: no cover – top‑level error handling
        log.error("Failed to generate manifest: %s", exc)
        return 1

    log.info("Successfully generated manifest with %d entries.", len(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
