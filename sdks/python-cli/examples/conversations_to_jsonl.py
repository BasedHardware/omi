import json
import os
import sys
from pathlib import Path


def extract_messages(conversation):
    """Extract and format transcript segments into standardized chat messages."""
    structured = conversation.get("structured") or {}
    title = structured.get("title") or "Untitled Conversation"
    
    messages = [
        {
            "role": "system",
            "content": f"You are reviewing an Omi conversation titled: {title}."
        }
    ]
    
    segments = conversation.get("transcript_segments") or []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        is_user = seg.get("is_user", True)
        role = "user" if is_user else "assistant"
        speaker = seg.get("speaker") or ("User" if is_user else "Speaker")
        
        messages.append({
            "role": role,
            "name": speaker.replace(" ", "_"),
            "content": text
        })
        
    return messages


def convert(source, destination):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = items.get("conversations") or items.get("items") or items.get("data") or [items]
    if not isinstance(items, list):
        raise ValueError("Expected a JSON array of conversations")

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    partial = output_path.with_name(output_path.name + ".partial")
    count = 0
    try:
        with open(partial, "w", encoding="utf-8") as out:
            for item in items:
                if not isinstance(item, dict):
                    continue
                conv_id = item.get("id")
                structured = item.get("structured") or {}
                messages = extract_messages(item)
                
                record = {
                    "id": conv_id,
                    "title": structured.get("title"),
                    "category": structured.get("category"),
                    "started_at": item.get("started_at"),
                    "finished_at": item.get("finished_at"),
                    "messages": messages
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise

    sys.stderr.write(f"Successfully converted {count} conversations to {destination}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_jsonl.py INPUT.json OUTPUT.jsonl")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL conversion failed: {exc}")
