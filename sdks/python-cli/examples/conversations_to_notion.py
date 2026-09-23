import argparse
import json
import os
import sys
from pathlib import Path


def create_heading_block(text):
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
        }
    }


def create_paragraph_block(speaker, text):
    content = f"{speaker}: {text}" if speaker else text
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
        }
    }


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json conversation list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        children = []
        for conv in items:
            if not isinstance(conv, dict):
                continue
            title = conv.get("title") or conv.get("id") or "Conversation"
            created_at = (conv.get("started_at") or conv.get("created_at") or "")[:10]
            heading_text = f"{title} ({created_at})" if created_at else title
            children.append(create_heading_block(heading_text))

            segments = conv.get("transcript_segments") or []
            if not segments and conv.get("text"):
                children.append(create_paragraph_block(None, conv["text"]))
            else:
                for seg in segments:
                    if isinstance(seg, dict):
                        speaker = seg.get("speaker") or "Speaker"
                        text = seg.get("text") or ""
                        if text:
                            children.append(create_paragraph_block(speaker, text))

        # Output directly formatted as Notion block children payload
        payload = {
            "children": children[:100]  # Notion maximum blocks per append request
        }

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Format Omi conversation transcripts for Notion block children API."
    )
    parser.add_argument("source", help="Path to input JSON file from 'omi --json conversation list'.")
    parser.add_argument("destination", nargs="?", default=None, help="Path to output JSON file.")
    parser.add_argument("-o", "--output", dest="output_flag", default=None, help="Path to output JSON file.")

    args = parser.parse_args()
    dest = args.output_flag or args.destination
    if not dest:
        parser.error("Destination JSON path must be provided either as a positional argument or via -o/--output flag.")

    try:
        convert(args.source, dest)
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
