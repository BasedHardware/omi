# Export Omi Conversations to JSON Lines (JSONL) for LLMs & RAG

Use this recipe to export recorded conversations, meeting overviews, and action
items captured by your Omi wearable device into standard JSON Lines (`.jsonl`)
format. The output is directly consumable by vector databases (ChromaDB, Pinecone,
Qdrant), RAG retrieval frameworks (LangChain, LlamaIndex), or fine-tuning pipelines
for personal and cloud LLMs (Ollama, OpenAI, Anthropic).

It reads saved JSON exports or reads directly from standard input (`-`), makes no
network requests, and writes one clean `.jsonl` file. You need Python 3.10+ and
an authenticated `omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to JSONL)

Stream up to 200 conversations directly into a `.jsonl` file:

```sh
omi --json conversation list --limit 200 | python conversations_to_jsonl.py - conversations.jsonl
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json conversation list --limit 200 > conversations.json
python conversations_to_jsonl.py conversations.json conversations.jsonl
```

### 3. Choose Target Schema Format

The converter provides three specialized output schemas:

- **`standard` (default):** Clean, flattened JSON records preserving conversation metadata and action items.
- **`rag`:** Formatted with `{"id": "...", "text": "...", "metadata": {...}}` for instant vector store chunk indexing.
- **`fine-tune`:** Chat completion format `{"messages": [...]}` tailored for instruction tuning on personal conversation summaries.

```sh
# Export for RAG vector search:
python conversations_to_jsonl.py conversations.json conv_rag.jsonl --format rag

# Export for LLM instruction fine-tuning:
python conversations_to_jsonl.py conversations.json conv_ft.jsonl --format fine-tune
```

---

## Converter Script

Save the following as `conversations_to_jsonl.py`:

```python
import argparse
import json
import sys
from pathlib import Path


def sanitize_text(value):
    """Render a loosely typed field as clean, single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def load_conversations(source):
    """Load conversations from stdin or a file path, ensuring valid list structure."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict) and "conversations" in data:
        data = data["conversations"]
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of conversations, got {type(data).__name__}")
    return data


def format_record(item, mode):
    """Format a single conversation item according to the specified output mode."""
    conv_id = item.get("id") or ""
    structured = item.get("structured") or {}
    title = sanitize_text(structured.get("title")) or "(untitled conversation)"
    overview = sanitize_text(structured.get("overview"))
    category = sanitize_text(structured.get("category")) or "general"
    started_at = item.get("started_at") or ""
    finished_at = item.get("finished_at") or ""
    source = item.get("source") or "omi"
    language = item.get("language") or ""
    action_items = [
        sanitize_text(ai.get("description"))
        for ai in structured.get("action_items", [])
        if ai.get("description")
    ]

    if mode == "rag":
        text_content = f"Title: {title}\nOverview: {overview}"
        return {
            "id": conv_id,
            "text": text_content,
            "metadata": {
                "title": title,
                "category": category,
                "started_at": started_at,
                "source": source,
                "language": language,
                "action_items_count": len(action_items)
            }
        }
    elif mode == "fine-tune":
        return {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a personal conversation assistant summarizing recorded meetings and discussions."
                },
                {
                    "role": "user",
                    "content": f"Can you give me a summary of the conversation titled '{title}'?"
                },
                {
                    "role": "assistant",
                    "content": overview if overview else "No detailed overview recorded for this session."
                }
            ]
        }
    else:  # standard
        return {
            "id": conv_id,
            "title": title,
            "overview": overview,
            "category": category,
            "started_at": started_at,
            "finished_at": finished_at,
            "source": source,
            "language": language,
            "action_items": action_items
        }


def convert(source, destination, mode, overwrite=False):
    """Convert input conversations to a destination JSONL file."""
    items = load_conversations(source)
    output_path = Path(destination)

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to force)")

    lines = []
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        conv_id = item.get("id")
        if conv_id and conv_id in seen_ids:
            continue
        if conv_id:
            seen_ids.add(conv_id)

        record = format_record(item, mode)
        lines.append(json.dumps(record, ensure_ascii=False))

    payload = "\n".join(lines) + ("\n" if lines else "")
    output_path.write_text(payload, encoding="utf-8")
    return len(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi conversations JSON export to JSON Lines (.jsonl).")
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

    print(f"Successfully converted {count} conversation{'s' if count != 1 else ''} to {args.destination} (mode: {args.format})")
```

---

## Schema Formats Reference

### Standard Format (`--format standard`)
```json
{"id": "conv_001", "title": "Weekly Engineering Sync", "overview": "Discussed system architecture.", "category": "work", "started_at": "2026-09-24T08:00:00Z", "action_items": ["Review PRs"]}
```

### RAG Ingestion Format (`--format rag`)
```json
{"id": "conv_001", "text": "Title: Weekly Engineering Sync\nOverview: Discussed system architecture.", "metadata": {"title": "Weekly Engineering Sync", "category": "work", "started_at": "2026-09-24T08:00:00Z"}}
```

### Fine-Tuning Format (`--format fine-tune`)
```json
{"messages": [{"role": "system", "content": "You are a personal conversation assistant."}, {"role": "user", "content": "Can you give me a summary of 'Weekly Engineering Sync'?"}, {"role": "assistant", "content": "Discussed system architecture."}]}
```
