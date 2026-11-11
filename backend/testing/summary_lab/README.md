# Conversation summary lab

Offline matrix: synthetic transcript → named variant → judged note + estimated cost.

Default seam is **recorded**. It never calls an LLM and never imports production
summarizer modules. `--live` is the opt-in path that calls
`get_conversation_notes`; keep that local and untracked if you point it at real
transcripts.

```bash
cd backend
python -m testing.summary_lab run --out /tmp/summary-lab
python -m testing.summary_lab compare --left /tmp/a/run.json --right /tmp/b/run.json
```

Fixtures in `testing/summary_lab/fixtures/` are synthetic. Do not commit customer
transcripts.
