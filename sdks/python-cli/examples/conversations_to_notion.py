import json
import os
import sys
from pathlib import Path

def make_rich_text(text, bold=False):
    return [{
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {"bold": bold}
    }]

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from omi --json conversation list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    blocks = []
    for conv in items:
        if not isinstance(conv, dict):
            continue
        title = (
            conv.get("structured", {}).get("title")
            if isinstance(conv.get("structured"), dict)
            else conv.get("title")
        ) or f"Conversation {conv.get('id', '')}"
        
        overview = (
            conv.get("structured", {}).get("overview")
            if isinstance(conv.get("structured"), dict)
            else conv.get("overview")
        ) or ""

        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": make_rich_text(title)}
        })

        if overview:
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": make_rich_text(overview),
                    "icon": {"emoji": "💡"}
                }
            })

        action_items = (
            conv.get("structured", {}).get("action_items")
            if isinstance(conv.get("structured"), dict)
            else conv.get("action_items", [])
        )
        if isinstance(action_items, list) and action_items:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": make_rich_text("Action Items")}
            })
            for act in action_items:
                act_text = act.get("description", str(act)) if isinstance(act, dict) else str(act)
                completed = act.get("completed", False) if isinstance(act, dict) else False
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": make_rich_text(act_text),
                        "checked": completed
                    }
                })

        segments = conv.get("transcript_segments", [])
        if isinstance(segments, list) and segments:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": make_rich_text("Transcript")}
            })
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                speaker = seg.get("speaker") or f"Speaker {seg.get('speaker_id', '0')}"
                stext = seg.get("text", "")
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{speaker}: "}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": stext[:1900]}}
                        ]
                    }
                })

        blocks.append({"object": "block", "type": "divider", "divider": {}})

    chunk_size = 100
    chunks = [blocks[i:i + chunk_size] for i in range(0, len(blocks), chunk_size)]
    payload = {
        "version": "2022-06-28",
        "total_blocks": len(blocks),
        "batch_count": len(chunks),
        "batches": chunks,
    }

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python conversations_to_notion.py <source.json> <destination.json>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
