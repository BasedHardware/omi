# Export Omi Memories to JSON Lines (JSONL) for LLMs & RAG

Use this recipe to export facts, preferences, and knowledge captured by your Omi
device into standard JSON Lines (`.jsonl`) format. The output is ready for direct
ingestion into vector databases (ChromaDB, Pinecone, Qdrant), RAG retrieval
pipelines (LangChain, LlamaIndex), or fine-tuning datasets for local and cloud
LLMs (Ollama, OpenAI, Anthropic).

It reads saved JSON exports or reads directly from standard input (`-`), makes no
network requests, and writes one clean `.jsonl` file. You need Python 3.10+ and
an authenticated `omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to JSONL)

Stream up to 200 memories directly into a `.jsonl` file:

```sh
omi --json memory list --limit 200 | python memories_to_jsonl.py - memories.jsonl
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json memory list --limit 200 > memories.json
python memories_to_jsonl.py memories.json memories.jsonl
```

### 3. Choose Target Schema Format

The converter supports three specialized output formats:

- **`standard` (default):** Clean, compact JSON objects preserving all original fields.
- **`rag`:** Formatted with `{"id": "...", "text": "...", "metadata": {...}}` for instant vector store chunk indexing.
- **`fine-tune`:** Chat completion format `{"messages": [...]}` tailored for instruction tuning and personalization fine-tuning.

```sh
# Export for RAG vector search:
python memories_to_jsonl.py memories.json memories_rag.jsonl --format rag

# Export for LLM instruction fine-tuning:
python memories_to_jsonl.py memories.json memories_ft.jsonl --format fine-tune
```

---

## Converter Script

Save the following as `memories_to_jsonl.py`:

```python
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sanitize_text(value):
    """Render a loosely typed field as clean, single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def load_memories(source):
    """Load memories from stdin or a file path, ensuring valid list structure."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")
    
    data = json.loads(content)
    if isinstance(data, dict) and "memories" in data:
        data = data["memories"]
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of memories, got {type(data).__name__}")
    return data


def format_record(item, mode):
    """Format a single memory item according to the specified output mode."""
    mem_id = item.get("id") or ""
    content = sanitize_text(item.get("content"))
    category = item.get("category") or "general"
    created_at = item.get("created_at") or ""
    source = item.get("source") or "omi"

    if mode == "rag":
        return {
            "id": mem_id,
            "text": content,
            "metadata": {
                "category": category,
                "created_at": created_at,
                "source": source
            }
        }
    elif mode == "fine-tune":
        return {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a personal AI memory assistant remembering user facts and learnings."
                },
                {
                    "role": "user",
                    "content": f"What did I record regarding {category}?"
                },
                {
                    "role": "assistant",
                    "content": content
                }
            ]
        }
    else:  # standard
        return {
            "id": mem_id,
            "content": content,
            "category": category,
            "created_at": created_at,
            "source": source
        }


def convert(source, destination, mode, overwrite=False):
    """Convert input memories to a destination JSONL file."""
    items = load_memories(source)
    output_path = Path(destination)

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to force)")

    lines = []
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        mem_id = item.get("id")
        if mem_id and mem_id in seen_ids:
            continue
        if mem_id:
            seen_ids.add(mem_id)
        
        record = format_record(item, mode)
        lines.append(json.dumps(record, ensure_ascii=False))

    payload = "\n".join(lines) + ("\n" if lines else "")
    output_path.write_text(payload, encoding="utf-8")
    return len(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi memories JSON export to JSON Lines (.jsonl).")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output .jsonl file.")
    parser.add_argument(
        "--format",
        choices=["standard", "rag", "fine-tune"],
        default="standard",
        help="Target JSONL schema: standard (default), rag (vector DB), or fine-tune (chat dataset)."
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists.")

    args = parser.parse_args()
    try:
        count = convert(args.source, args.destination, args.format, overwrite=args.overwrite)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")
    
    print(f"Successfully converted {count} memory record{'s' if count != 1 else ''} to {args.destination} (mode: {args.format})")
```

---

## Schema Formats Reference

### Standard Format (`--format standard`)
```json
{"id": "mem_001", "content": "User prefers concise technical summaries.", "category": "preferences", "created_at": "2026-09-24T01:15:00Z", "source": "conversation"}
```

### RAG Ingestion Format (`--format rag`)
```json
{"id": "mem_001", "text": "User prefers concise technical summaries.", "metadata": {"category": "preferences", "created_at": "2026-09-24T01:15:00Z", "source": "conversation"}}
```

### Fine-Tuning Format (`--format fine-tune`)
```json
{"messages": [{"role": "system", "content": "You are a personal AI memory assistant remembering user facts and learnings."}, {"role": "user", "content": "What did I record regarding preferences?"}, {"role": "assistant", "content": "User prefers concise technical summaries."}]}
```
