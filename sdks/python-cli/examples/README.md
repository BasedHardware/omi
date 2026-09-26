# omi-cli — Examples

Standalone recipes that show how to combine `omi-cli` with shell pipelines,
Python scripts, and AI agent harnesses.

---

## Index

| Example | Format | Description |
|---|---|---|
| [`agent_quickstart.md`](agent_quickstart.md) | Guide | First agent harness: fetch memories, post a conversation, close the loop. |
| [`agent_quickstart.ms.md`](agent_quickstart.ms.md) | Guide (Malay) | Malay translation of the agent quickstart guide. |
| [`memories_to_jsonl.py`](memories_to_jsonl.py) | Script | Export memories to JSON Lines — SFT chat format or structured knowledge records. |
| [`memories_jsonl.md`](memories_jsonl.md) | Guide | Full documentation for `memories_to_jsonl.py`: CLI usage, schema reference, fine-tuning integration. |

---

## Usage pattern

Most scripts read from **stdin or a file** and write to **stdout or a file**,
so they compose naturally with `omi --json` and `jq`:

```bash
omi --json memory list \
  | python examples/memories_to_jsonl.py - -o dataset.jsonl
```

See each example's own `.md` file for full documentation.
