# Convert conversation exports to line-delimited JSON (JSONL)

Use this recipe to convert Omi conversation exports into clean, compact, line-delimited JSON (JSONL).
JSONL is the industry standard format for:
- Vector database embedding pipelines (Pinecone, Qdrant, ChromaDB, Weaviate, pgvector)
- LLM fine-tuning datasets (OpenAI, Anthropic, Hugging Face, Llama)
- Big Data batch processing (pandas, DuckDB, Apache Spark)
- Unix command-line streaming with `jq`, `grep`, and `awk`

This recipe relies strictly on the Python standard library, makes zero network requests, supports streaming via standard input/output (pipes), and implements atomic exclusive file writing to guard against accidental overwrites.

## 1. Export conversations

Export conversations to JSON using `omi-cli`:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Or stream directly without intermediate files:

```sh
omi --json conversation list --limit 200 | python conversations_to_jsonl.py - -o conversations.jsonl
```

## 2. Python Script (`conversations_to_jsonl.py`)

A full reference script is available at [`conversations_to_jsonl.py`](conversations_to_jsonl.py).

### CLI Usage

```sh
# Basic conversion (metadata, overview, action items)
python conversations_to_jsonl.py conversations.json -o conversations.jsonl

# Include full transcript segments (ideal for RAG and fine-tuning)
python conversations_to_jsonl.py conversations.json --include-transcript -o conversations.jsonl

# Filter by category (case-insensitive, comma-separated)
python conversations_to_jsonl.py conversations.json --category work,meeting -o filtered.jsonl

# Pipe from stdin to stdout
cat conversations.json | python conversations_to_jsonl.py - > output.jsonl
```

## 3. Output Record Format

Each line is a valid, standalone JSON object with compact formatting (`separators=(",", ":")`), encoded in UTF-8 without ASCII escaping (`ensure_ascii=False` to preserve multilingual text, emojis, and accents).

### Schema (Default)

```json
{
  "id": "c_12345",
  "created_at": "2026-10-15T12:00:00Z",
  "started_at": "2026-10-15T12:00:00Z",
  "finished_at": "2026-10-15T12:30:00Z",
  "source": "omi",
  "language": "en",
  "category": "work",
  "title": "Sprint Planning",
  "overview": "Reviewed sprint backlog and finalized delivery goals.",
  "emoji": "🚀",
  "action_items": [
    {
      "description": "Deploy firmware update",
      "completed": false
    }
  ],
  "events": []
}
```

### Schema (with `--include-transcript`)

Adds the `transcript_segments` array containing ordered speaker utterances and timestamps:

```json
{
  "id": "c_12345",
  "title": "Sprint Planning",
  "transcript_segments": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 3.5,
      "text": "Let's review the sprint objectives."
    }
  ]
}
```

## 4. Key Design & Resilience Features

- **Standard Library Only**: Requires no external dependencies (`pip install`).
- **Resilient Envelope Unwrapping**: Gracefully handles raw lists, single conversation dictionaries, or paginated envelopes (`conversations`, `data`, `items`, `results`).
- **Normalized Timestamps**: Normalizes ISO-8601 strings to standard UTC `YYYY-MM-DDTHH:MM:SSZ` while safely tolerating boundary overflow cases (e.g., year > 9999).
- **Surrogate & BOM Immunity**: Automatically handles UTF-8 Byte Order Marks (BOM) from Windows tools and strips lone surrogate code points to prevent decoding crashes.
- **Atomic Exclusive Creation**: When writing to a file (`-o/--output`), writes to an adjacent temporary file and commits atomically, rejecting overwrites if the target file already exists (`FileExistsError`).
