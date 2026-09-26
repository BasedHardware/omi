# Export memories to JSON Lines (.jsonl) for AI fine-tuning & RAG

Use this recipe when you want to feed your Omi memories, facts, learnings, and personal knowledge into machine learning models, retrieval-augmented generation (RAG) vector stores, or LLM system context windows. It reads one or more JSON exports or accepts piped input from `omi-cli`, makes no network requests, and complements [`memories_markdown.md`](memories_markdown.md) and [`conversations_to_jsonl.py`](conversations_jsonl.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## Quick start

Export memories directly to JSON Lines:

```sh
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_jsonl.py - -o memories.jsonl
```

Export with specific formatting modes:

```sh
# RAG mode: pre-formatted text + metadata for Chroma, Pinecone, or LangChain
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o rag_memories.jsonl --mode rag

# System Prompt mode: ready-to-inject system instructions for persona alignment
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o system_prompts.jsonl --mode system_prompt

# Filter by category (e.g. work and skills)
python sdks/python-cli/examples/memories_to_jsonl.py memories.json -o work_knowledge.jsonl --category work,skills
```

## Output Modes

### 1. `standard` (default)
Strict one-line-per-record format with normalized timestamps and structured arrays:

```json
{"id": "mem_01", "content": "Prefers asynchronous communication for architecture proposals.", "category": "work", "visibility": "private", "tags": ["workflow", "management"], "created_at": "2026-09-15T10:30:00+00:00", "updated_at": "2026-09-15T10:35:00+00:00"}
```

### 2. `rag`
Ready-to-index document format with payload text and vector search metadata:

```json
{"id": "mem_01", "text": "[WORK] Prefers asynchronous communication for architecture proposals.", "metadata": {"id": "mem_01", "category": "work", "visibility": "private", "tags": ["workflow", "management"], "created_at": "2026-09-15T10:30:00+00:00"}}
```

### 3. `system_prompt`
Formatted conversational system context for prompt injection:

```json
{"role": "system", "content": "User memory (work): Prefers asynchronous communication for architecture proposals. (#workflow, #management)", "memory_id": "mem_01"}
```

## Deduplication & Merging

When merging exports across multiple pages, pass multiple files:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py page1.json page2.json page3.json -o combined.jsonl
```

Duplicate memory IDs are automatically deduplicated. To preserve raw duplicates, pass `--no-dedupe`.
