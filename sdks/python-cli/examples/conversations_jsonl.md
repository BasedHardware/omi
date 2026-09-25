# Convert Conversations to JSON Lines (JSONL) Dataset

Use this recipe to convert exported Omi conversation transcripts and summaries into standard JSON Lines (`.jsonl`) datasets. The resulting files are immediately compatible with multi-turn conversational LLM fine-tuning (OpenAI, Anthropic, Llama, Mistral) or structured transcript extraction for RAG knowledge bases.

This recipe uses only Python standard library modules (`json`, `pathlib`, `argparse`, `sys`), requires zero third-party dependencies, and executes offline.

---

## 1. Export Your Conversations

Export conversations including transcript segments using `omi-cli`:

```sh
omi conversation list --include-transcript --limit 100 --json > conversations.json
```

Or convert directly via pipeline from `stdin`:

```sh
omi conversation list --include-transcript --limit 50 --json | python sdks/python-cli/examples/conversations_to_jsonl.py - -o conversations.jsonl
```

---

## 2. Multi-Turn Conversational SFT Format (`--format chat`)

Run `conversations_to_jsonl.py` with the default `chat` format:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py conversations.json -o sft_dataset.jsonl
```

### Output Schema (Chat)

Each line is a self-contained JSON object following standard OpenAI / Anthropic conversational messages schema:

```json
{
  "id": "conv_101",
  "title": "Quarterly Product Architecture",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful personal assistant with detailed knowledge of the user's recorded conversations, meetings, and discussions."
    },
    {
      "role": "user",
      "content": "Let's review the memory sync pipeline before the release."
    },
    {
      "role": "assistant",
      "content": "[Alex]: Agreed, the local SQLite cache is fully tested and ready."
    }
  ]
}
```

You can customize the system instruction using `--system-prompt`:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py conversations.json -o custom_sft.jsonl --system-prompt "You are an executive assistant summarizing meeting notes."
```

---

## 3. Structured Transcript & Knowledge Format (`--format transcript`)

For full-text indexing, vector embeddings, or RAG search evaluation, use `--format transcript`:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py conversations.json -o transcripts.jsonl --format transcript
```

### Output Schema (Transcript)

```json
{
  "id": "conv_101",
  "title": "Quarterly Product Architecture",
  "category": "engineering",
  "overview": "Reviewed memory sync pipeline and verified SQLite caching.",
  "transcript": "SPEAKER_00: Let's review the memory sync pipeline before the release.\nSPEAKER_01: Agreed, the local SQLite cache is fully tested and ready.",
  "started_at": "2026-09-24T14:30:00Z",
  "metadata": {
    "source": "omi_necklace",
    "segment_count": 2
  }
}
```

---

## 4. Multi-File Deduplication & Safe I/O

You can pass multiple paginated export files. Conversations sharing the same `id` are automatically deduplicated in memory:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py page1.json page2.json page3.json -o full_dataset.jsonl
```

### Overwrite Protection
By default, the script refuses to overwrite an existing destination file. Use `-f` / `--force` to explicitly overwrite:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py conversations.json -o sft_dataset.jsonl --force
```
