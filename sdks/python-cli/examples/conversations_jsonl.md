# Convert conversation transcripts to JSONL for LLM fine-tuning and RAG

Use this recipe to convert your Omi conversation transcripts into JSON Lines (`.jsonl`)
format, the standard format for fine-tuning LLMs (such as OpenAI, Anthropic, or LLaMA)
and indexing into Retrieval-Augmented Generation (RAG) vector pipelines. It reads a
saved JSON export, makes no network requests, and requires zero external dependencies.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 conversations with transcript details:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `conversations_to_jsonl.py`:

```python
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
                
                # Format compatible with OpenAI, Anthropic, and LLaMA fine-tuning datasets
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
```

Run the converter:

```sh
python conversations_to_jsonl.py conversations.json conversations.jsonl
```

Each line in the resulting `.jsonl` file is an independent JSON object with a
standardized `messages` array, ready for ingestion into OpenAI Fine-Tuning,
HuggingFace datasets, or RAG embeddings. The converter refuses to overwrite an
existing destination, and a failed run leaves no partial file behind. Treat
the exported file as private personal conversation data.
