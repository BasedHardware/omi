# Convert a conversation-list export to JSON Lines (.jsonl)

Use this recipe to convert your Omi conversation history into JSON Lines
(`.jsonl`) format. JSONL is the standard format for fine-tuning LLMs, streaming
records into vector databases (Chroma, Pinecone, LanceDB), and building RAG
(Retrieval-Augmented Generation) search indexes.

Each line in the resulting `.jsonl` file is an independent, valid JSON document,
allowing large datasets to be processed line-by-line without loading the entire
file into memory.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## 1. Export Conversations

Export up to 200 conversations to JSON:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations_0.json
```

Or pipe directly from standard input:

```sh
omi --json conversation list | python conversations_to_jsonl.py - -o fine_tune.jsonl --mode fine_tune
```

## 2. Save the Converter Script

Save the following code as `conversations_to_jsonl.py`:

```python
#!/usr/bin/env python3
"""
Convert Omi conversation-list JSON exports to JSON Lines (.jsonl) for AI fine-tuning, RAG, and vector databases.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


def parse_datetime(iso_str: Optional[str]) -> Optional[str]:
    """Normalize ISO-8601 timestamp string to standard UTC ISO text."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except (ValueError, AttributeError):
        return str(iso_str)


def read_conversations(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Read and unwrap conversation records across one or more files or stdin."""
    all_items: List[Dict[str, Any]] = []
    for source in inputs:
        if source == "-":
            raw = sys.stdin.read().lstrip("\ufeff")
            src_name = "<stdin>"
        else:
            p = Path(source)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {source}")
            raw = p.read_text(encoding="utf-8").lstrip("\ufeff")
            src_name = source

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {src_name}: {exc}") from exc

        if isinstance(parsed, dict):
            for key in ("conversations", "items", "data"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break

        if not isinstance(parsed, list):
            raise ValueError(f"{src_name}: expected a JSON array or wrapped object")

        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError(f"{src_name}: each record must be a JSON object")
            if not item.get("id"):
                raise ValueError(f"{src_name}: conversation missing required 'id' field")
            all_items.append(item)

    return all_items


def format_record(item: Dict[str, Any], mode: str = "standard") -> Dict[str, Any]:
    """Format a conversation record according to the selected mode."""
    conv_id = str(item.get("id"))
    structured: Dict[str, Any] = item.get("structured") or {}
    title = str(structured.get("title") or item.get("title") or "").strip()
    category = structured.get("category") or item.get("category")
    overview = str(structured.get("overview") or "").strip()
    transcript = str(item.get("transcript") or "").strip()
    action_items = structured.get("action_items") or []
    source = item.get("source")
    started_at = parse_datetime(item.get("started_at"))
    created_at = parse_datetime(item.get("created_at"))
    updated_at = parse_datetime(item.get("updated_at"))

    if mode == "fine_tune":
        messages: List[Dict[str, str]] = []
        user_prompt = f"Topic: {title}" if title else "Meeting Conversation"
        if overview:
            user_prompt += f"\nOverview: {overview}"
        messages.append({"role": "user", "content": user_prompt})
        messages.append({"role": "assistant", "content": transcript if transcript else overview})
        return {
            "conversation_id": conv_id,
            "messages": messages,
        }

    if mode == "rag":
        text_parts: List[str] = []
        if title:
            text_parts.append(f"Title: {title}")
        if category:
            text_parts.append(f"Category: {category}")
        if overview:
            text_parts.append(f"Overview: {overview}")
        if transcript:
            text_parts.append(f"Transcript:\n{transcript}")

        return {
            "id": conv_id,
            "text": "\n\n".join(text_parts),
            "metadata": {
                "title": title,
                "category": category,
                "source": source,
                "started_at": started_at,
                "created_at": created_at,
            },
        }

    # standard mode
    return {
        "id": conv_id,
        "title": title,
        "category": category,
        "source": source,
        "started_at": started_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "overview": overview,
        "action_items": action_items,
        "transcript": transcript,
    }


def convert(
    inputs: Sequence[str],
    output_path: str,
    mode: str = "standard",
    category_filter: Optional[str] = None,
    dedupe: bool = True,
) -> int:
    """Read conversation inputs and write formatted lines to output_path. Returns count written."""
    out = Path(output_path)
    if ".." in out.parts:
        raise ValueError(f"Output path {output_path!r} contains '..'; refusing to write.")

    items = read_conversations(inputs)
    seen_ids: Set[str] = set()
    written_count = 0

    lines: List[str] = []
    for item in items:
        conv_id = str(item.get("id"))
        if dedupe and conv_id in seen_ids:
            continue
        seen_ids.add(conv_id)

        structured: Dict[str, Any] = item.get("structured") or {}
        cat = structured.get("category") or item.get("category")
        if category_filter and (not cat or cat.lower() != category_filter.lower()):
            continue

        record = format_record(item, mode=mode)
        lines.append(json.dumps(record, ensure_ascii=False))
        written_count += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return written_count


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation-list JSON exports into JSON Lines (.jsonl)."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="JSON_FILE",
        help="One or more conversation JSON files (or '-' for stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="JSONL_FILE",
        help="Output destination path for .jsonl file.",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["standard", "fine_tune", "rag"],
        default="standard",
        help="Output JSONL formatting mode (default: standard).",
    )
    parser.add_argument(
        "-c",
        "--category",
        help="Filter conversations by category (case-insensitive).",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable deduplication across input files.",
    )

    args = parser.parse_args(argv)

    try:
        count = convert(
            inputs=args.inputs,
            output_path=args.output,
            mode=args.mode,
            category_filter=args.category,
            dedupe=not args.no_dedupe,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {count} conversations to {args.output} in '{args.mode}' mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 3. Run Conversions

### Standard Export
Converts conversations preserving all structured metadata and raw transcript:
```sh
python conversations_to_jsonl.py conversations_0.json -o conversations.jsonl
```

### LLM Instruction / Fine-Tuning Format
Formats conversations into multi-turn chat messages compatible with OpenAI, Anthropic, and Gemini fine-tuning:
```sh
python conversations_to_jsonl.py conversations_0.json -o fine_tune.jsonl --mode fine_tune
```

### Vector Database / RAG Chunking
Formats each conversation into combined text and metadata ready for vector indexing:
```sh
python conversations_to_jsonl.py conversations_0.json -o rag_index.jsonl --mode rag --category work
```

### Merging Multiple Pages
Provide multiple JSON pages; duplicate conversations sharing the same `id` are automatically deduplicated:
```sh
python conversations_to_jsonl.py page1.json page2.json page3.json -o full_archive.jsonl
```

## 4. Querying and Processing

Inspect entries with `jq`:

```sh
jq -c '{id, title, category}' conversations.jsonl
```

Stream lines directly in Python:

```python
import json

with open("conversations.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        print(f"[{doc['id']}] {doc['title']} ({doc['category']})")
```
