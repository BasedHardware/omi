# Sync utilities

This package owns uploaded-audio sync admission, decoding, transcription orchestration, persistence fencing, and playback reconstruction.

## Boundaries

- `pipeline.py` is the coordinator. It owns job/run leases, segment processing, persistence fences, and terminal outcomes.
- `files.py`, `content_id.py`, and `capture_manifest.py` validate and normalize uploaded files and their identities.
- `lanes.py`, `backfill.py`, and `rate_limit.py` classify work and enforce admission policy.
- `merge_audio.py` and `merge_dedupe.py` contain deterministic merge helpers.
- `playback.py` reconstructs and serves persisted audio artifacts.
- `provenance.py` and `telemetry.py` provide bounded attribution and operational labels.

Keep HTTP routing and database implementations outside this package. New helpers should remain deterministic where possible; changes that mutate a sync job must preserve the run-lease and conversation-persistence fences in `pipeline.py`.

## Cross-job assignment and relevance

`lifecycle.ingest_sync_conversation` admits uploads through
`database.conversations.assign_sync_conversation`. Its Firestore transaction reads
and writes `users/{uid}/sync_assignment/recent` and the selected conversation
atomically. `assignment.py` owns the transaction body and speaker-independent
shape policy. The legacy timestamp query supplies a hint only. `_OrderedTurnstile`
is a within-job optimization, not a cross-process lock. The index retains 128
recent intervals; the existing query remains the historical lookup.

A 120-second gap, matching source, and compatible known device IDs admit a merge.
Missing device IDs retain legacy time-based behavior. Sync-owned recordings dedupe
absolute ranges, not repeated narration text. A `sync_content_revision` fences
stale processing writes after an append. Storage errors propagate into the existing
retry path; they must never fall through to an uncoordinated create.

Short filler-only content gets `sync_relevance=review`, keeps a visible transcript
and deterministic title, and skips automatic LLM enrichment. Subsequent intake
reassesses the whole transcript. Unknown content and language stay `keep`; neither
speaker profiles nor `is_user` affect this gate. This is transcript-only demotion,
not a client review-folder feature or a classifier for video versus real speech.
See root `HANDOFF.md` for remaining verification and edge cases.
