import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def hash_file(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def convert(source_dir, destination):
    src = Path(source_dir)
    if not src.is_dir():
        raise ValueError(f"Source must be a directory containing audio recordings: {src}")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        audio_extensions = {".wav", ".mp3", ".m4a", ".opus", ".flac", ".ogg", ".aac", ".pcm"}
        manifest = []

        for p in sorted(src.rglob("*")):
            if p.is_file() and p.suffix.lower() in audio_extensions:
                stat = p.stat()
                manifest.append({
                    "filename": p.name,
                    "relative_path": str(p.relative_to(src)).replace("\\", "/"),
                    "size_bytes": stat.st_size,
                    "modified_at": int(stat.st_mtime),
                    "sha256": hash_file(p),
                    "format": p.suffix.lstrip(".").lower()
                })

        output = {
            "source_directory": str(src.resolve()),
            "total_files": len(manifest),
            "total_bytes": sum(item["size_bytes"] for item in manifest),
            "chunks": manifest,
        }

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Index raw audio chunk directories into a verified SHA-256 JSON manifest."
    )
    parser.add_argument(
        "source_dir",
        help="Path to directory containing audio recordings."
    )
    parser.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Path to output JSON manifest file."
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_flag",
        default=None,
        help="Path to output JSON manifest file (alternative to positional argument)."
    )

    args = parser.parse_args()

    dest = args.output_flag or args.destination
    if not dest:
        parser.error("Destination JSON path must be provided either as a positional argument or via -o/--output flag.")

    try:
        convert(args.source_dir, dest)
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
