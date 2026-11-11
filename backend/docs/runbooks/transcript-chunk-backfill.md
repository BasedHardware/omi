# Transcript chunk backfill

For explicit transcript recall, prefer the direct paginated search described in
`../transcript-recall.md`: it searches saved old/new transcripts without a
backfill. This runbook remains the separately approved operator repair for the
legacy semantic chunk index. Do not enable the retired
`TRANSCRIPT_CHUNK_INDEXING_ENABLED` flag; it no longer selects a writer.

Legacy semantic chat search can query transcript-chunk vectors (`ns_tchunks`),
but normal processing does not maintain complete coverage after #20959.
Unindexed history needs this repair only for that legacy semantic path;
explicit direct transcript recall reads saved text without it.
`backend/scripts/backfill_transcript_chunk_vectors.py` indexes one user's
completed, visible conversations with the same chunking search readers rebuild.

## When to use

A specific account reports that chat or search misses something it said, and the
reply notes that older or unindexed transcripts may still contain it (#20629).
This is a per-account repair. It does not index conversations recorded after the
run.

## Run

Use the approved production identity, with the backend environment for the target
project (Firestore, the encryption secret, Pinecone, and embeddings). Resolve the
UID privately from the support report. Never paste it into a public issue or PR.

1. Dry-run: `python scripts/backfill_transcript_chunk_vectors.py --uid <uid>`. It
   reads Firestore and prints counts only. `chunks` is the number of embeddings
   `--apply` will create, which is its cost; get sign-off on that before applying.
2. Optional canary: add `--apply --limit 20` to index the 20 newest conversations.
3. Apply: `python scripts/backfill_transcript_chunk_vectors.py --uid <uid> --apply`.
4. Verify: ask chat about a fact known to be only in that account's transcripts.
   The answer should cite a verbatim transcript excerpt.

## Reading the result

- Exit 0: every eligible conversation was fully indexed.
- Exit 1: `failed_conversations` is nonzero. Rerun the same command. Vector IDs
  are deterministic, so a rerun overwrites rather than duplicating.
- Exit 2: no vector index is configured in this environment; nothing was written.
- `removed_after_delete`: conversations the user deleted mid-run. Their chunks
  were removed again, so no derived vectors outlive a deletion.

Conversations recorded after the run are not indexed. Rerun for the account if
it needs later history to be searchable too.
