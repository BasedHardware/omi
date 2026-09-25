"""
Convert Omi action item exports to standard JSON Lines (JSONL) datasets.
Supports conversational SFT (OpenAI / Anthropic message format) and structured task records.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


DEFAULT_SYSTEM_PROMPT = (
    "You are a personal task assistant. Extract action items, due dates, and completion status from context."
)


def validate_and_normalize_record(record: Any) -> Optional[Dict[str, Any]]:
    """Validate raw action item object and return normalized representation or None if invalid/empty."""
    if not isinstance(record, dict):
        return None

    item_id = record.get("id")
    if not item_id or not isinstance(item_id, str):
        return None

    description = record.get("description") or record.get("content") or record.get("text")
    if description is None:
        return None
    if not isinstance(description, str):
        description = str(description)
    description = description.strip()
    if not description:
        return None

    # Skip deleted items if explicitly marked
    if record.get("deleted") is True or str(record.get("deleted")).lower() == "true":
        return None

    completed_raw = record.get("completed")
    if isinstance(completed_raw, bool):
        completed = completed_raw
    elif isinstance(completed_raw, (int, float)):
        completed = bool(completed_raw)
    elif isinstance(completed_raw, str):
        completed = completed_raw.strip().lower() in ("true", "1", "yes", "completed")
    else:
        completed = False

    created_at = record.get("created_at") or record.get("created")
    if created_at is not None and not isinstance(created_at, str):
        created_at = str(created_at)

    updated_at = record.get("updated_at") or record.get("updated")
    if updated_at is not None and not isinstance(updated_at, str):
        updated_at = str(updated_at)

    due_date = record.get("due_date") or record.get("due_at") or record.get("due")
    if due_date is not None and not isinstance(due_date, str):
        due_date = str(due_date)

    conversation_id = record.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        conversation_id = str(conversation_id)

    return {
        "id": item_id,
        "description": description,
        "completed": completed,
        "status": "completed" if completed else "open",
        "created_at": created_at,
        "updated_at": updated_at,
        "due_date": due_date,
        "conversation_id": conversation_id,
    }


def format_chat_entry(item: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    """Render an entry in standard OpenAI/Anthropic/HuggingFace conversational SFT format."""
    description = item["description"]
    status_str = "Completed" if item["completed"] else "Pending"
    due_str = f"\nDue Date: {item['due_date']}" if item.get("due_date") else ""
    conv_ref = f" (Conversation: {item['conversation_id']})" if item.get("conversation_id") else ""

    user_prompt = f"What action items or follow-ups were recorded{conv_ref}?"
    assistant_reply = f"Action Item: {description}\nStatus: {status_str}{due_str}"

    return {
        "id": item["id"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_reply},
        ],
    }


def format_record_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """Render an entry in standard metadata-rich task record format for search or databases."""
    return {
        "id": item["id"],
        "description": item["description"],
        "completed": item["completed"],
        "status": item["status"],
        "due_date": item["due_date"],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "metadata": {
            "conversation_id": item["conversation_id"],
        },
    }


def convert_action_items(
    sources: List[str | Path],
    destination: str | Path,
    output_format: str = "task-extraction",
    status_filter: str = "all",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    force: bool = False,
) -> Tuple[int, int]:
    """
    Read action items from one or more JSON source files (or stdin) and write to JSONL.
    Returns (total_records_processed, unique_records_written).
    """
    seen_ids: Set[str] = set()
    rows_to_write: List[str] = []
    total_processed = 0

    for src in sources:
        if str(src) == "-":
            try:
                raw_bytes = sys.stdin.buffer.read()
                content = json.loads(raw_bytes.decode("utf-8-sig"))
            except Exception as err:
                raise ValueError(f"Malformed JSON from standard input: {err}") from err
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")

            try:
                content = json.loads(path.read_bytes().decode("utf-8-sig"))
            except Exception as err:
                raise ValueError(f"Malformed JSON in {path}: {err}") from err

        if isinstance(content, dict):
            # Tolerate envelope objects: {"action_items": [...]} or {"items": [...]} or {"data": [...]}
            content = content.get("action_items") or content.get("items") or content.get("data") or [content]

        if not isinstance(content, list):
            raise ValueError(f"Expected a JSON array of action items, got {type(content).__name__}")

        for raw_item in content:
            total_processed += 1
            item = validate_and_normalize_record(raw_item)
            if not item:
                continue

            # Apply status filter
            if status_filter == "open" and item["completed"]:
                continue
            if status_filter == "completed" and not item["completed"]:
                continue

            item_id = item["id"]
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            if output_format == "task-extraction":
                entry = format_chat_entry(item, system_prompt)
            else:
                entry = format_record_entry(item)

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
        description="Convert Omi action item JSON exports to JSON Lines (.jsonl) for AI fine-tuning or task databases."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON files (or '-' for stdin) from omi action-item list --json")
    parser.add_argument("-o", "--output", required=True, help="Destination .jsonl output file")
    parser.add_argument(
        "--format",
        choices=["task-extraction", "task-record"],
        default="task-extraction",
        help="Target schema: 'task-extraction' (OpenAI SFT messages) or 'task-record' (clean structured record)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by status: 'all', 'open', or 'completed' (default: all)",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="Custom system prompt for task-extraction schema",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    args = parser.parse_args(argv)

    try:
        total, written = convert_action_items(
            sources=args.inputs,
            destination=args.output,
            output_format=args.format,
            status_filter=args.status,
            system_prompt=args.system_prompt,
            force=args.force,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Successfully processed {total} action items -> {written} unique JSONL rows written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
