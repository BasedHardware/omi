# Convert Memories to JSON Lines (JSONL) Dataset

Use this recipe to convert exported Omi memories, facts, and learnings into standard JSON Lines (`.jsonl`) datasets. The resulting files are immediately compatible with LLM fine-tuning pipelines (OpenAI, Anthropic, HuggingFace) or vector/RAG knowledge extraction tools.

This recipe uses only Python standard library modules (`json`, `pathlib`, `argparse`), requires no third-party dependencies, and executes offline.

---

## 1. Export Your Memories

Export up to 200 memories using `omi-cli`:

```sh
omi memory list --limit 200 --json > memories.json
```

For large memory bases across multiple pages, you can export multiple files:

```sh
omi memory list --limit 200 --offset 0 --json > memories_page1.json
omi memory list --limit 200 --offset 200 --json > memories_page2.json
```

---

## 2. Convert to Fine-Tuning Format (`--format chat`)

Run `memories_to_jsonl.py` with the default `chat` format:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o dataset.jsonl
```

### Output Schema (Chat)

Each line is a self-contained JSON object following standard conversational SFT formatting:

```json
{
  "id": "mem_101",
  "messages": [
    {
      "role": "system",
      "content": "You are a personal assistant with comprehensive recall of the user's memories, facts, and context."
    },
    {
      "role": "user",
      "content": "What do you know regarding my preferences?"
    },
    {
      "role": "assistant",
      "content": "User prefers dark mode and Python over TypeScript."
    }
  ]
}
```

You can customize the system instruction using `--system-prompt`:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o custom_dataset.jsonl --system-prompt "You are Omi, a friendly personal memory copilot."
```

---

## 3. Convert to Knowledge / RAG Format (`--format knowledge`)

For vector database ingest, RAG evaluation, or embedding generation, use `--format knowledge`:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o knowledge.jsonl --format knowledge
```

### Output Schema (Knowledge)

```json
{
  "id": "mem_101",
  "text": "User prefers dark mode and Python over TypeScript.",
  "category": "preferences",
  "created_at": "2026-09-20T08:00:00Z",
  "metadata": {
    "conversation_id": "conv_402",
    "updated_at": "2026-09-20T08:00:00Z"
  }
}
```

---

## 4. Multi-File Deduplication and Safe I/O

You can pass multiple JSON files. Records sharing the same memory `id` are automatically deduplicated in memory so that only one unique entry is emitted:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories_page1.json memories_page2.json -o combined_dataset.jsonl
```

### Overwrite Protection
By default, the script will refuse to overwrite an existing destination file. To explicitly overwrite an existing file, provide the `-f` / `--force` flag:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o dataset.jsonl --force
```

---

## 5. Direct Training Integration

### OpenAI Fine-Tuning CLI
Validate the generated dataset directly using OpenAI's CLI:

```sh
openai tools fine_tunes.prepare_data -f dataset.jsonl
```

### HuggingFace Datasets
Load the dataset in Python with one line:

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="dataset.jsonl")
print(dataset["train"][0])
```
