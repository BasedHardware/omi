# Export Omi Action Items to JSON Lines (JSONL) Dataset

Convert and stream action items captured by your Omi wearable device into standard **JSON Lines (`.jsonl`)** format.

This recipe supports two primary workflows:
1. **`--format task-extraction` (Default)**: Conversational instruction-tuning format compatible with OpenAI Fine-Tuning API, Anthropic, and HuggingFace SFT trainers (`{"messages": [...]}`).
2. **`--format task-record`**: Clean, metadata-rich structured JSONL records ideal for vector databases (Chroma, Pinecone, Qdrant), analytical data warehouses (BigQuery, DuckDB, Snowflake), or task sync pipelines.

---

## Prerequisites

Ensure the `omi` CLI is installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can view action items:

```sh
omi action-item list
```

---

## Quickstart

### 1. Direct Pipeline Stream (Stdout to JSONL)

Pipe your active action items directly from the CLI into a fine-tuning dataset:

```sh
omi --json action-item list | python action_items_to_jsonl.py - -o action_items.jsonl
```

### 2. Export Pending / Open Tasks Only

Filter out completed action items to train on outstanding tasks:

```sh
omi --json action-item list | python action_items_to_jsonl.py - --status open -o pending_tasks.jsonl
```

### 3. Structured Task Records for Vector / Analytics Stores

Export as clean records with timestamps and conversation lineage:

```sh
python action_items_to_jsonl.py raw_export.json --format task-record -o task_records.jsonl
```

### 4. Merge and Deduplicate Multi-Page Exports

Provide multiple files from paginated exports—duplicate task IDs are automatically resolved:

```sh
python action_items_to_jsonl.py page1.json page2.json page3.json -o full_tasks.jsonl --force
```

---

## Schema Specifications

### Format 1: `task-extraction` (Conversational SFT)

Each row is a single self-contained JSON object ready for OpenAI fine-tuning:

```json
{
  "id": "act_8829104",
  "messages": [
    {
      "role": "system",
      "content": "You are a personal task assistant. Extract action items, due dates, and completion status from context."
    },
    {
      "role": "user",
      "content": "What action items or follow-ups were recorded (Conversation: conv_99214)?"
    },
    {
      "role": "assistant",
      "content": "Action Item: Send quarterly pitch deck to investors\nStatus: Pending\nDue Date: 2026-10-01T17:00:00Z"
    }
  ]
}
```

### Format 2: `task-record` (Structured Metadata Record)

Optimized for database loading, embedding models, and search pipelines:

```json
{
  "id": "act_8829104",
  "description": "Send quarterly pitch deck to investors",
  "completed": false,
  "status": "open",
  "due_date": "2026-10-01T17:00:00Z",
  "created_at": "2026-09-25T14:30:00Z",
  "updated_at": "2026-09-25T14:35:00Z",
  "metadata": {
    "conversation_id": "conv_99214"
  }
}
```

---

## Downstream Integrations

### OpenAI Fine-Tuning CLI

Validate and start training directly on your generated dataset using the modern OpenAI CLI (v1.0+):

```sh
# 1. Format dataset
omi --json action-item list | python action_items_to_jsonl.py - -o tasks_train.jsonl

# 2. Upload training file
openai files create -f tasks_train.jsonl -p "fine-tune"

# 3. Launch fine-tuning job
openai fine_tuning jobs create -t "file-XYZ" -m "gpt-4o-mini-2024-07-18"
```

> **Note on Strict SFT Loaders**: The `task-extraction` format includes a top-level `id` key for lineage tracking in HuggingFace `datasets` and analytical tools. If using a strict third-party trainer that requires only the `messages` key, you can strip the ID during export:
> ```sh
> python action_items_to_jsonl.py export.json -o - | jq -c '{messages: .messages}' > clean_train.jsonl
> ```

> **Privacy & Data Ownership Reminder**: Uploading personal action items to third-party fine-tuning APIs shares recorded tasks and due dates with that provider. Ensure confidential or sensitive tasks are filtered (e.g., via `--status` or pre-scrubbing) prior to remote uploads.

### HuggingFace `datasets` (Python)

Load your exported records into a Pandas DataFrame or HuggingFace Dataset in two lines:

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="task_records.jsonl")
print(f"Loaded {len(dataset['train'])} action items")
```

---

## Command-Line Reference

| Argument | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more input JSON files, or `-` for standard input | *(Required)* |
| `--output` | `-o` | Target `.jsonl` output path | *(Required)* |
| `--format` | `--format` | Target schema: `task-extraction` or `task-record` | `task-extraction` |
| `--status` | `--status` | Filter items by status: `all`, `open`, or `completed` | `all` |
| `--system-prompt` | `--system-prompt` | Custom system prompt for `task-extraction` format | Built-in default |
| `--force` | `-f` | Overwrite destination file if it already exists | `False` |

---

## Design Principles

- **Standard Library Only**: Requires no external dependencies (`json`, `sys`, `pathlib`, `argparse`).
- **Resilient Parsing**: Supports standard JSON lists and enveloped responses (`{"action_items": [...]}`).
- **BOM Protection**: Automatically strips UTF-8 Byte Order Marks generated by Windows PowerShell stdout.
- **Idempotent Deduplication**: Cross-file deduplication keyed on unique action item ID (first-occurrence-wins preserving export order).
- **Atomic File Safety**: Writes to new files safely (`xb` mode), preventing accidental data loss unless `--force` is passed.
