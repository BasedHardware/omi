# conversations_to_jsonl.py

A tiny command‑line helper that turns a plain‑text conversation transcript into a
JSONL file ready for LLM fine‑tuning or Retrieval‑Augmented Generation (RAG).

## Why JSONL?

- **Line‑delimited** – each line is a single JSON object, making it easy to stream.
- **Standard format** – most LLM fine‑tuning pipelines (OpenAI, Anthropic, etc.) accept JSONL.
- **RAG‑friendly** – you can later split the JSONL into chunks and embed them.

## Input format

The script expects a **simple, line‑oriented transcript** where each line starts
with a speaker label followed by a colon (`:`) and the utterance text.

