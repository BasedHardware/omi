# Memories → JSON Lines (JSONL) Dataset Recipe

Convert your Omi memories, facts, and learnings into `.jsonl` datasets ready
for SFT fine-tuning or structured knowledge pipelines — using nothing but the
standard library.

---

## Prerequisites

```bash
pipx install omi-cli   # or: pip install omi-cli
export OMI_API_KEY="<your key>"  # https://app.omi.me/apps/your-account
```

The conversion script (`memories_to_jsonl.py`) has **zero third-party
dependencies** — Python ≥ 3.8 is all you need.

---

## Quick start

```bash
# 1. Fetch memories as JSON and pipe straight into the converter:
omi --json memory list | python examples/memories_to_jsonl.py - -o dataset.jsonl

# 2. Inspect the result:
head -n 3 dataset.jsonl | python -m json.tool --no-ensure-ascii
```

---

## Output formats

Pass `--format <schema>` to choose the output shape.  The default is `chat`.

### `--format chat`  (default)

OpenAI / Anthropic / HuggingFace-compatible messages schema.
Each memory becomes a single-turn assistant completion:

```jsonc
{
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant with knowledge about the user's experiences, facts, and learnings captured by Omi."
    },
    {
      "role": "user",
      "content": "What do you know about this?"
    },
    {
      "role": "assistant",
      "content": "I enjoy trail running on weekends and prefer early morning starts."
    }
  ]
}
```

This format uploads directly to the [OpenAI fine-tuning
API](https://platform.openai.com/docs/guides/fine-tuning) and to HuggingFace
`datasets.load_dataset("json", ...)`.

### `--format knowledge`

Structured extraction with full metadata — useful for RAG indexing, knowledge
graph ingestion, or analytics:

```jsonc
{
  "id": "mem_01j9zx4kab",
  "content": "I enjoy trail running on weekends and prefer early morning starts.",
  "category": "hobbies",
  "created_at": "2025-01-15T07:42:00+00:00",
  "source": null
}
```

---

## CLI reference

```
usage: memories_to_jsonl.py INPUT [INPUT ...] -o OUTPUT [--format {chat,knowledge}]

positional arguments:
  INPUT     JSON input file(s) — JSON array or NDJSON. Use '-' for stdin.

options:
  -o, --output  Destination .jsonl file. Use '-' or '/dev/stdout' for stdout.
  --format      Output schema: 'chat' (default) or 'knowledge'.
```

---

## Pipeline recipes

### Fetch → convert → validate in one line

```bash
omi --json memory list \
  | python examples/memories_to_jsonl.py - -o memories.jsonl \
  && wc -l memories.jsonl
```

### Filter by category before converting

```bash
omi --json memory list --categories work,skills \
  | python examples/memories_to_jsonl.py - -o work_skills.jsonl
```

### Merge multiple exports and deduplicate

Records are deduplicated by `id` across all inputs — safe to re-run daily:

```bash
python examples/memories_to_jsonl.py \
    exports/2024.json exports/2025.json \
    -o dataset.jsonl --format knowledge
```

### Stream to `jq` for inspection

```bash
omi --json memory list \
  | python examples/memories_to_jsonl.py - -o - --format knowledge \
  | jq 'select(.category == "health") | .content'
```

### Count tokens before uploading to OpenAI

```bash
pip install tiktoken  # one-off, not required by the script itself

python - <<'EOF'
import json, tiktoken
enc = tiktoken.encoding_for_model("gpt-4o-mini")
total = 0
with open("memories.jsonl") as f:
    for line in f:
        total += len(enc.encode(json.loads(line)["messages"][-1]["content"]))
print(f"{total:,} tokens")
EOF
```

---

## Fine-tuning integration

### OpenAI

```bash
# Validate format first:
openai tools fine_tunes.prepare_data -f memories.jsonl

# Upload and create a fine-tuning job:
openai api fine_tuning.jobs.create \
  -t memories.jsonl \
  -m gpt-4o-mini-2024-07-18
```

### HuggingFace `datasets`

```python
from datasets import load_dataset

ds = load_dataset("json", data_files="memories.jsonl", split="train")
print(ds[0])
```

### Axolotl / LLaMA-Factory

Both tools accept the `chat` format directly. Point your YAML config at the
`.jsonl` file:

```yaml
# axolotl config excerpt
datasets:
  - path: memories.jsonl
    type: sharegpt
    conversation: chatml
```

---

## JSONL schema reference

### `chat` record

| Field | Type | Description |
|---|---|---|
| `messages` | `array` | Ordered list of role/content pairs |
| `messages[].role` | `"system"\|"user"\|"assistant"` | Speaker |
| `messages[].content` | `string` | Message text |

### `knowledge` record

| Field | Type | Description |
|---|---|---|
| `id` | `string\|null` | Omi memory ID |
| `content` | `string` | Memory text |
| `category` | `string\|null` | Category label (e.g. `"work"`, `"health"`) |
| `created_at` | `string\|null` | ISO-8601 UTC timestamp |
| `source` | `string\|null` | Plugin or capture source ID |

---

## Atomic writes and safety

The script writes to a sibling `.jsonl.tmp` file first, then atomically
replaces the destination via `Path.replace()`.  A crash mid-write never leaves
a partial file at the target path.

---

## Related examples

- [`agent_quickstart.md`](agent_quickstart.md) — drive Omi from an LLM agent
- [`README.md`](README.md) — full examples index
