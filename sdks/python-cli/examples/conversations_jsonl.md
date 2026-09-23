# conversations_to_jsonl – Convert transcripts to JSONL

Fine‑tuning or Retrieval‑Augmented Generation (RAG) pipelines for large language
models often expect data in **JSON Lines (JSONL)** format, where each line is a
JSON object representing a single conversation.

This recipe shows how to turn a simple, human‑readable transcript into that
format using the `conversations_to_jsonl.py` helper script.

---

## 📄 Expected transcript format

The script works with a plain‑text file where each utterance is on its own line
and is prefixed by the speaker name followed by a colon:

