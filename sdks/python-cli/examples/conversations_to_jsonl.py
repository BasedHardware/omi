import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


def clean_text(value):
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return " ".join(value.split())


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_conversations(sources):
    """Load and deduplicate conversations from multiple JSON source files."""
    conv_map = OrderedDict()
    for source in sources:
        path = Path(source)
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array from 'omi --json conversation list'")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each conversation entry must be a JSON object")
            conv_id = raw.get("id")
            if not isinstance(conv_id, str) or not conv_id:
                raise ValueError(f"{source}: conversation item missing non-empty string 'id'")
            conv_map[conv_id] = raw
    return list(conv_map.values())


def format_conversation_record(raw, mode="standard", system_prompt="You are a personal conversation assistant."):
    """Format single conversation record into desired target dictionary."""
    conv_id = clean_text(raw.get("id"))
    start_dt = parse_time(raw.get("started_at"))
    end_dt = parse_time(raw.get("finished_at"))

    seconds = 0
    if start_dt and end_dt and end_dt >= start_dt:
        seconds = int((end_dt - start_dt).total_seconds())

    structured = raw.get("structured") if isinstance(raw.get("structured"), dict) else {}
    title = clean_text(structured.get("title")) or "(untitled conversation)"
    overview = clean_text(structured.get("overview"))
    category = clean_text(structured.get("category")) or "general"
    action_items_raw = structured.get("action_items")
    action_items = [clean_text(a) for a in action_items_raw if clean_text(a)] if isinstance(action_items_raw, list) else []

    start_iso = start_dt.isoformat() if start_dt else None
    end_iso = end_dt.isoformat() if end_dt else None

    if mode == "chat":
        # Multi-turn chat format for fine-tuning
        user_prompt = f"Summarize the conversation titled '{title}'."
        assistant_content = overview if overview else f"Conversation '{title}' categorized under {category}."
        if action_items:
            assistant_content += f"\nAction Items: {'; '.join(action_items)}"

        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_content}
            ],
            "metadata": {
                "id": conv_id,
                "started_at": start_iso,
                "category": category,
                "duration_seconds": seconds
            }
        }
    elif mode == "rag":
        # Document format optimized for semantic search / RAG vector embedding
        text_parts = [f"Title: {title}", f"Category: {category}"]
        if start_iso:
            text_parts.append(f"Recorded Date: {start_iso}")
        if overview:
            text_parts.append(f"Overview: {overview}")
        if action_items:
            text_parts.append("Action Items: " + ", ".join(action_items))

        return {
            "id": conv_id,
            "text": "\n".join(text_parts),
            "metadata": {
                "id": conv_id,
                "title": title,
                "category": category,
                "started_at": start_iso,
                "duration_seconds": seconds,
                "language": clean_text(raw.get("language")),
                "folder": clean_text(raw.get("folder_name"))
            }
        }
    else:  # standard
        return {
            "id": conv_id,
            "title": title,
            "category": category,
            "overview": overview,
            "action_items": action_items,
            "started_at": start_iso,
            "finished_at": end_iso,
            "duration_seconds": seconds,
            "language": clean_text(raw.get("language")),
            "folder": clean_text(raw.get("folder_name")),
            "source": clean_text(raw.get("source"))
        }


def convert(sources, destination, mode="standard", category_filter=None, system_prompt="You are a personal conversation assistant."):
    """Load conversations, format records into JSONL, and write to file."""
    conversations = load_conversations(sources)
    if category_filter:
        cat_lower = category_filter.lower()
        filtered = []
        for c in conversations:
            struct = c.get("structured") or {}
            c_cat = clean_text(struct.get("category")).lower()
            if c_cat == cat_lower:
                filtered.append(c)
        conversations = filtered

    lines = []
    for c in conversations:
        rec = format_conversation_record(c, mode=mode, system_prompt=system_prompt)
        lines.append(json.dumps(rec, ensure_ascii=False))

    output_path = Path(destination)
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None

    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = "standard"
    category_filter = None
    system_prompt = "You are a personal conversation assistant."

    while args and args[0].startswith("--"):
        if args[0] == "--format":
            if len(args) < 2 or args[1] not in ("standard", "chat", "rag"):
                sys.exit("Error: --format requires one of: standard, chat, rag")
            mode = args[1]
            args = args[2:]
        elif args[0] == "--category":
            if len(args) < 2:
                sys.exit("Error: --category requires a string argument")
            category_filter = args[1]
            args = args[2:]
        elif args[0] == "--system-prompt":
            if len(args) < 2:
                sys.exit("Error: --system-prompt requires a string argument")
            system_prompt = args[1]
            args = args[2:]
        else:
            sys.exit(f"Unknown option: {args[0]}")

    if len(args) < 2:
        sys.exit("Usage: python conversations_to_jsonl.py [--format standard|chat|rag] [--category CAT] OUTPUT.jsonl INPUT.json [INPUT.json ...]")

    dest = args[0]
    srcs = args[1:]
    try:
        count = convert(srcs, dest, mode=mode, category_filter=category_filter, system_prompt=system_prompt)
        print(f"Exported {count} conversation records to {dest}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
