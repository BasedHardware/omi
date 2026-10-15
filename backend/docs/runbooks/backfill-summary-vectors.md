# Summary-vector backfill

Use this per-user operator tool after deploying the chat vector freshness repair,
when completed conversations missed their Pinecone `ns1` summary upserts under
the JIT/finalization fence. It regenerates embeddings and overwrites deterministic
`{uid}-{conversation_id}` IDs; reruns are safe. This is a one-time repair, not a
scheduled job. Oct 9's `backfill_transcript_chunk_vectors.py` is the transcript-chunk
analog; this tool repairs summary vectors only.

From `backend/`, with the operator-approved environment and worktree venv:

```sh
python scripts/backfill_summary_vectors.py --uid <uid> --dry-run
python scripts/backfill_summary_vectors.py --uid <uid> --since 2026-08-01T00:00:00Z --limit 50 --apply
```

Default: dry-run, since August 1 2026 UTC, at most 500 eligible rows, newest-first.
Selection stops after `10 * --limit` scanned documents (5,000 by default),
including ineligible rows; Firestore page reads share this cap, so sparse histories
may select fewer than `--limit` rows.
Only completed, non-discarded, non-deleted rows with nonempty summary title or
overview qualify. Dry-run reads metadata/summary fields only, with no transcripts,
embedding calls or vector reads/writes. Output contains counts, never content or
conversation IDs. Obtain cost and production-write sign-off on the selected count
before `--apply`: each selected row costs one fresh embedding plus the existing
metadata-extraction LLM calls (including retries), filter-catalog writes, vector
fetch/upsert and conversation reads. No production execution is part of the implementing PR.

JSON counts: `scanned`, `selected`, `created`, `updated`, `error`, and
`stopped_error_budget`. Created/updated distinguish whether the vector ID existed
before the upsert. Missing provider configuration cannot report a successful write.
Writes re-read visibility and clean up vectors if deletion/discard happens during
indexing. Failures log only the exception class and continue within a total error
budget of floor(10% of the selected batch); exceeding it stops further writes.
For batches below ten, the first error exceeds the budget. Retry after diagnosing
the failure; already successful rows will be updated.

Exit codes: 0 = preview or all selected writes succeeded; 1 = at least one row
failed (including an error-budget stop); 2 = invalid arguments or unconfigured
vector index. Selection/read failures terminate nonzero and must be investigated.
Monitor `omi_conversation_summary_vector_upserts_total` and the “Conversation search
freshness” row on Omi Core Features. These counters measure write activity, not
proof that every historic conversation is indexed. No alert rules are added.
