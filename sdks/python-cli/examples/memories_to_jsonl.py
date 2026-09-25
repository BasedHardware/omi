"""
Convert Omi memory exports to standard JSON Lines (JSONL) datasets.
Supports conversational SFT (OpenAI / Anthropic message format) and structured knowledge extraction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


DEFAULT_SYSTEM_PROMPT = "You are a personal assistant with comprehensive recall of the user's memories, facts, and context."


def validate_and_normalize_record(record: Any) -> Optional[Dict[str, Any]]:
    """Validate raw memory object and return normalized representation or None if invalid/empty."""
    if not isinstance(record, dict):
        return None

    mem_id = record.get("id")
    if not mem_id or not isinstance(mem_id, str):
        return None

    content = record.get("content")
    if content is None:
        return None
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    if not content:
        return None

    # Skip deleted items if explicitly marked
    if record.get("deleted") is True or str(record.get("deleted")).lower() == "true":
        return None

    category = record.get("category")
    if category is not None and not isinstance(category, str):
        category = str(category)
    category = (category or "general").strip()

    created_at = record.get("created_at") or record.get("created")
    if created_at is not None and not isinstance(created_at, str):
        created_at = str(created_at)

    updated_at = record.get("updated_at") or record.get("updated")
    if updated_at is not None and not isinstance(updated_at, str):
        updated_at = str(updated_at)

    conversation_id = record.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        conversation_id = str(conversation_id)

    return {
        "id": mem_id,
        "content": content,
        "category": category,
        "created_at": created_at,
        "updated_at": updated_at,
        "conversation_id": conversation_id,
    }


def format_chat_entry(item: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    """Render an entry in standard OpenAI/Anthropic/HuggingFace SFT format."""
    category = item.get("category", "general")
    content = item.get("content", "")

    user_prompt = (
        f"What do you know regarding my {category}?"
        if category != "general"
        else "What do you remember about this topic?"
    )

    return {
        "id": item["id"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": content},
        ],
    }


def format_knowledge_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """Render an entry in standard metadata-rich knowledge extraction/RAG format."""
    return {
        "id": item["id"],
        "text": item["content"],
        "category": item["category"],
        "created_at": item["created_at"],
        "metadata": {
            "conversation_id": item["conversation_id"],
            "updated_at": item["updated_at"],
        },
    }


def convert_memories(
    sources: List[str | Path],
    destination: str | Path,
    output_format: str = "chat",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    force: bool = False,
) -> Tuple[int, int]:
    """
    Read memories from one or more JSON source files and stream to output JSONL.
    Returns (total_records_processed, unique_records_written).
    """
    seen_ids: Set[str] = set()
    rows_to_write: List[str] = []
    total_processed = 0

    for src in sources:
        path = Path(src)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")

        try:
            content = json.loads(path.read_bytes())
        except Exception as err:
            raise ValueError(f"Malformed JSON in {path}: {err}") from err

        if not isinstance(content, list):
            raise ValueError(f"Expected a JSON array of memories in {path}, got {type(content).__name__}")

        for raw_item in content:
            total_processed += 1
            item = validate_and_normalize_record(raw_item)
            if not item:
                continue

            mem_id = item["id"]
            if mem_id in seen_ids:
                continue
            seen_ids.add(mem_id)

            if output_format == "chat":
                entry = format_chat_entry(item, system_prompt)
            else:
                entry = format_knowledge_entry(item)

            line = json.dumps(entry, ensure_ascii=False)
            rows_to_write.append(line)

    payload = ("\n".join(rows_to_write) + ("\n" if rows_to_write else "")).encode("utf-8")
    dest_path = Path(destination)

    # Protect existing destination unless force=True
    mode = "wb" if force else "xb"
    try:
        with dest_path.open(mode) as f:
            f.write(payload)
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing file '{dest_path}'. Use --force to overwrite.") from None
    except OSError:
        dest_path.unlink(missing_ok=True)
        raise

    return total_processed, len(rows_to_write)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to JSON Lines (.jsonl) for LLM fine-tuning or knowledge datasets."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON files exported from omi memory list --json")
    parser.add_argument("-o", "--output", required=True, help="Destination .jsonl output file")
    parser.add_argument(
        "--format",
        choices=["chat", "knowledge"],
        default="chat",
        help="Target schema: 'chat' (OpenAI/Anthropic conversational messages) or 'knowledge' (text + metadata)",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System instruction for conversational messages (used in 'chat' format)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists",
    )

    args = parser.parse_args(argv)

    try:
        total, written = convert_memories(
            sources=args.inputs,
            destination=args.output,
            output_format=args.format,
            system_prompt=args.system_prompt,
            force=args.force,
        )
        print(f"Successfully converted {written} memories ({total} processed) into '{args.output}'")
        return 0
    except (FileNotFoundError, ValueError, FileExistsError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
