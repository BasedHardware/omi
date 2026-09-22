# Convert conversations export to JSON Lines (JSONL)

Use this recipe to prepare Omi conversation exports for LLM fine-tuning, RAG embedding pipelines, or streaming JSONL ingest. It reads a saved JSON export from `omi --json conversation list --include-transcript` and formats each conversation as a single line JSON record. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export conversations with transcripts:

```sh
omi --json conversation list --include-transcript --limit 100 > conversations.json
```

Convert to JSONL:

```sh
python conversations_to_jsonl.py conversations.json conversations.jsonl
```

Emits valid JSON Lines with atomic file replacement.
