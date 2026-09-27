# Omi Memories Batch Pipeline (JSONL & CSV)

Use this recipe to stream, deduplicate, filter, and convert Omi memory JSON exports into **JSONL** (for LLM fine-tuning and RAG vector databases) or **CSV** (for spreadsheets and tabular data science).

It reads one or more exported JSON files or streams via standard input, merges paginated records by ID, and guarantees zero external dependencies (Python standard library only).

You need Python 3.9+ and an authenticated `omi-cli`.

---

## 1. Export Memories from Omi CLI

Export paginated memories from your Omi account:

```sh
# Export first page
omi --json memory list --limit 100 --offset 0 > memories_page1.json

# Export second page
omi --json memory list --limit 100 --offset 100 > memories_page2.json
```

Or stream directly via pipe:

```sh
omi --json memory list --limit 200 | python memories_pipeline.py - -o dataset.jsonl
```

---

## 2. Multi-Page Deduplication & Formats

The companion script `memories_pipeline.py` automatically resolves duplicate memory IDs across pages (retaining the most recently updated entry) and writes clean records.

### A. Convert to JSONL for LLMs & Vector Databases

JSONL (newline-delimited JSON) is the industry standard for RAG embeddings and LLM ingestion:

```sh
python memories_pipeline.py memories_page1.json memories_page2.json -o memories.jsonl
```

#### LLM Fine-Tuning Format (`--schema chat`)
To format records directly as conversational training messages (OpenAI, Gemini, or LLaMA chat format):

```sh
python memories_pipeline.py memories.json -o fine_tune.jsonl --schema chat
```

Output record structure:
```json
{
  "messages": [
    {"role": "system", "content": "You are a personal memory retrieval assistant. Recall facts and knowledge accurately."},
    {"role": "user", "content": "What do you remember regarding work?"},
    {"role": "assistant", "content": "Working on Omi open-source bounty program"}
  ],
  "metadata": {"id": "mem-2222", "created_at": "2026-09-21T09:00:00Z", "tags": ["omi", "bounty"]}
}
```

### B. Convert to CSV for Spreadsheets

Convert into a sanitized CSV file for Excel, Google Sheets, or Pandas:

```sh
python memories_pipeline.py memories.json -o memories.csv
```

---

## 3. Filtering & Privacy Controls

### Filter by Categories
Keep only specific memory categories (e.g. `work` and `learnings`):

```sh
python memories_pipeline.py memories.json -o work_memories.jsonl --category work,learnings
```

### Exclude Private Memories
Omit any memory marked with `visibility: private`:

```sh
python memories_pipeline.py memories.json -o public_memories.csv --no-private
```

---

## 4. Pipeline Streaming with Unix Tools

Because JSONL outputs one JSON document per line, downstream processing with `jq`, `grep`, or `wc` is effortless:

```sh
# Count exported memories
omi --json memory list | python memories_pipeline.py - | wc -l

# Search for specific topic with jq
python memories_pipeline.py memories.json - | jq 'select(.category == "work") | .content'
```

---

## 5. Security & Product Invariants

- **Zero External Dependencies**: Pure Python standard library (`argparse`, `csv`, `datetime`, `io`, `json`, `pathlib`, `sys`).
- **100% Offline & Air-Gapped**: Zero network requests or tracking telemetry.
- **Formula Injection Defense**: CSV exports sanitize leading `=`, `+`, `-`, `@` characters with a leading single quote.
- **Path Traversal Guard**: Rejects destination paths containing `..` to prevent directory traversal.
- **Atomic Creation**: Refuses to overwrite existing files unless explicitly instructed with `-f` or `--force`.
