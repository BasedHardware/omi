# Export Omi Conversations to JSONL (LLM Fine-Tuning & RAG)

Use this recipe to export your Omi conversation transcripts and summaries into structured **JSONL (JSON Lines)** format. The exported datasets are ideal for fine-tuning custom LLMs (OpenAI Chat format), ingestion into Vector Databases / RAG pipelines (LangChain, LlamaIndex, Pinecone, ChromaDB), or data archiving.

## Requirements

- Python 3.10+
- An authenticated `omi-cli` (`omi auth login`)

## Quickstart

### Option 1: Direct Pipeline via Stdin (Recommended)

Fetch your recent conversations with full audio transcript segments and stream them directly into a fine-tuning dataset:

```bash
omi --json conversation list --include-transcript --limit 100 | python conversations_to_jsonl.py - --output ./dataset.jsonl --format chat
```

### Option 2: Export from a Saved JSON File

1. Export conversations to a local JSON file:
   ```bash
   omi --json conversation list --include-transcript --limit 50 > conversations.json
   ```

2. Convert to JSONL:
   ```bash
   python conversations_to_jsonl.py conversations.json --output ./conversations.jsonl --format chat
   ```

## Supported Export Formats

| Format | Flag | Description | Use Case |
|---|---|---|---|
| **Chat** (Default) | `-f chat` | Formats each conversation as standard OpenAI messages (`system`, `user`, `assistant`). | LLM Supervised Fine-Tuning (SFT), LoRA training |
| **RAG** | `-f rag` | Full structured text chunks with metadata (`title`, `category`, `date`, `speaker`). | Vector Databases, Embeddings, Semantic Search |
| **Raw** | `-f raw` | Clean single-line JSON records preserving all original fields. | Data lakes, BigQuery, Pandas processing |

### Customizing System Prompt for Fine-Tuning

When using `--format chat`, you can customize the system instructions embedded in each training sample:

```bash
python conversations_to_jsonl.py input.json -o ./sft_train.jsonl -f chat --system-prompt "You are a personalized AI executive assistant summarizing daily meeting transcripts."
```
