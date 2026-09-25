# Omi Memories to JSON Lines (JSONL) Dataset Recipe

Export Omi memories, facts, and learnings into standard JSON Lines format for LLM fine-tuning, embedding models, or vector database ingestion.

## Requirements
- Python 3.8+
- Omi CLI installed (`pip install omi`)

## Installation
No additional dependencies required. Uses only Python standard library.

## Usage

### Export memories to JSONL
```bash
# Export all memories to memories.jsonl
omi memories export --format jsonl --output memories.jsonl

# Export with UTC offset for timezone localization
omi memories export --format jsonl --output memories.jsonl --utc-offset +09:00

# Export with pagination and deduplication
omi memories export --format jsonl --output memories.jsonl --page-size 100 --pages 5
```

### JSONL Output Structure
Each line contains a single JSON record:

```json
{
  "id": "unique-memory-id",
  "content": "memory content text",
  "category": "fact|learning|memory",
  "visibility": "public|private",
  "created_at": "2023-01-01T12:00:00+09:00",
  "updated_at": "2023-01-02T12:00:00+09:00",
  "tags": ["tag1", "tag2"],
  "raw": {
    "original": "...",
    "metadata": {
      "source": "...",
      "confidence": 0.95
    }
  }
}
```

### Key Features
- **Standard JSONL Format**: Single JSON record per line
- **Timezone Support**: Optional UTC offset for localized timestamps
- **Tag Normalization**: Converts arrays/comma-strings to standardized tag lists
- **Deduplication**: Safely merges paginated exports by memory ID
- **Atomic Writes**: Uses `xb` mode to prevent accidental overwrites

## Use Cases
- LLM fine-tuning datasets (OpenAI, Anthropic, Llama)
- Embedding model training
- Vector database ingestion for RAG pipelines

## Example Pipeline
```bash
# Export memories
omi memories export --format jsonl --output dataset.jsonl

# Ingest into vector database
python -m langchain.vectorstores.chroma ingest --input dataset.jsonl
```