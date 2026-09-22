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
                    "format": p.suffix.lower().lstrip("."),
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python audio_chunks_to_manifest.py <audio_directory> <destination.json>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
