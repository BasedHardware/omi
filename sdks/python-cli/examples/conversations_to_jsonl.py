import json
import os
import sys
from pathlib import Path


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Extract structured summary or transcripts for LLM fine-tuning/RAG record
                record = {
                    "id": item.get("id"),
                    "title": item.get("structured", {}).get("title") if isinstance(item.get("structured"), dict) else item.get("title"),
                    "category": item.get("structured", {}).get("category") if isinstance(item.get("structured"), dict) else item.get("category"),
                    "overview": item.get("structured", {}).get("overview") if isinstance(item.get("structured"), dict) else None,
                    "action_items": item.get("structured", {}).get("action_items") if isinstance(item.get("structured"), dict) else [],
                    "transcript_segments": item.get("transcript_segments", []),
                    "started_at": item.get("started_at"),
                    "finished_at": item.get("finished_at"),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python conversations_to_jsonl.py <source.json> <destination.jsonl>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
