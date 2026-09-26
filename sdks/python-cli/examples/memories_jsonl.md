# Export your memories to JSON Lines (JSONL)

Use this recipe to export Omi memories, facts, and learnings to standard JSON
Lines (`.jsonl`) for AI fine-tuning, retrieval-augmented generation (RAG)
pipelines, embedding generation, or vector database ingestion. It turns one or
more `memory list` exports into clean, normalized JSONL lines with support for
deduplication across multiple pages, category filtering, and direct conversion
into OpenAI/Gemini/Anthropic chat fine-tuning format (`--format chat`). It reads
saved JSON exports, makes zero network requests, and refuses to overwrite
existing files. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the export succeeded before converting. To include more records,
increment `--offset` by 200 into separate files (`memories_200.json`, etc.).

Save the following as `memories_to_jsonl.py`:

```python
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
    """Parse an ISO-8601 timestamp into normalized UTC ISO-8601 string, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def load_memories(sources):
    """Load and deduplicate memories from multiple JSON source files."""
    memories_map = OrderedDict()
    for source in sources:
        path = Path(source)
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array from 'omi --json memory list'")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each memory entry must be a JSON object")
            mem_id = raw.get("id")
            if not isinstance(mem_id, str) or not mem_id:
                raise ValueError(f"{source}: memory item missing non-empty string 'id'")
            memories_map[mem_id] = raw
    return list(memories_map.values())


def format_record(raw, mode="standard", system_prompt="You are a personal memory assistant."):
    """Transform memory record into desired output dictionary format."""
    content = clean_text(raw.get("content"))
    category = clean_text(raw.get("category")) or "general"
    created_at = parse_time(raw.get("created_at"))
    updated_at = parse_time(raw.get("updated_at"))
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    cleaned_tags = [clean_text(t) for t in tags if clean_text(t)]

    if mode == "chat":
        user_query = f"What do you remember about my {category} context?" if category != "general" else "Recall this memory."
        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": content}
            ],
            "metadata": {
                "id": raw["id"],
                "category": category,
                "created_at": created_at
            }
        }
    elif mode == "completion":
        return {
            "prompt": f"Omi memory [{category}]:\n",
            "completion": f" {content}"
        }
    else:  # standard
        return {
            "id": raw["id"],
            "content": content,
            "category": category,
            "tags": cleaned_tags,
            "created_at": created_at,
            "updated_at": updated_at,
            "manually_added": bool(raw.get("manually_added")),
            "conversation_id": raw.get("conversation_id")
        }


def convert(sources, destination, mode="standard", category_filter=None, system_prompt="You are a personal memory assistant."):
    """Read memories, filter, format, and write lines to destination file."""
    memories = load_memories(sources)
    if category_filter:
        cat_lower = category_filter.lower()
        memories = [m for m in memories if clean_text(m.get("category")).lower() == cat_lower]

    lines = []
    for m in memories:
        rec = format_record(m, mode=mode, system_prompt=system_prompt)
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
    system_prompt = "You are a personal memory assistant."

    while args and args[0].startswith("--"):
        if args[0] == "--format":
            if len(args) < 2 or args[1] not in ("standard", "chat", "completion"):
                sys.exit("Error: --format requires one of: standard, chat, completion")
            mode = args[1]
            args = args[2:]
        elif args[0] == "--category":
            if len(args) < 2:
                sys.exit("Error: --category requires a filter argument")
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
        sys.exit("Usage: python memories_to_jsonl.py [--format standard|chat|completion] [--category CAT] OUTPUT.jsonl INPUT.json [INPUT.json ...]")

    dest = args[0]
    srcs = args[1:]
    try:
        count = convert(srcs, dest, mode=mode, category_filter=category_filter, system_prompt=system_prompt)
        print(f"Exported {count} memory records to {dest}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
```

Run it (the output file comes first, then one or more exports):

```sh
# Standard JSONL export
python memories_to_jsonl.py memories.jsonl memories_0.json memories_200.json

# Fine-tuning chat format for LLMs
python memories_to_jsonl.py --format chat training_data.jsonl memories_0.json
```

Each row in the output file is a single valid JSON object followed by a newline,
making it ready for ingestion by Hugging Face `datasets`, OpenAI fine-tuning,
vector stores (Chroma, Pinecone, Qdrant), or pandas/Spark dataframes.
