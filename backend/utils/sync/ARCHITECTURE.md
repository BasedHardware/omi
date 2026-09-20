# Sync utilities

This package owns uploaded-audio sync admission, decoding, transcription orchestration, persistence fencing, and playback reconstruction.

## Boundaries

- `pipeline.py` coordinates job/run leases, segment processing, persistence fences, and terminal outcomes.
- `files.py`, `content_id.py`, and `capture_manifest.py` normalize uploads and identities. Capture assignment never grants fresh-lane provenance.
- `capture.py` derives retry-stable incoming IDs from the VAD-segment timestamp. VAD exports speech segments only; empty VAD/STT creates no conversation or bridge and bills no speech.
- `lanes.py`, `backfill.py`, and `rate_limit.py` classify work and enforce admission policy.
- `merge_audio.py` and `merge_dedupe.py` contain deterministic merge helpers; `playback.py` reconstructs audio artifacts.
- `provenance.py` and `telemetry.py` provide bounded attribution and operational labels.

Keep HTTP routing and database implementations outside this package. Changes must preserve run-lease, durable result, and conversation-persistence fences in `pipeline.py`.

## Capture assignment

The 2026-09-19 incident was **sync adopting live-flap stubs**: failed live STT caused reconnects about every 35 seconds, creating empty conversations with near-zero extent. The legacy timestamp lookup chose a different nearest stub for each 60-second WAL, even within an ordered job. The observed jobs were legacy backfill without explicit targets or turnstile timeouts. Cross-job lookup/create races addressed by #15106 are a separate, older class.

`lifecycle.ingest_sync_conversation` admits uploads through `database.conversations.assign_sync_conversation`. `assignment.py` computes connected capture components in one Firestore transaction, using codecs supplied by the database adapter. Every transactional read precedes writes. Decode/storage errors propagate; there is no uncoordinated create fallback.

`assignment_index.py` stores metadata-only UTC day buckets under `users/{uid}/sync_assignment`. Every occupied day indexes the component. Buckets do not evict entries; Firestore size limits fail visibly. The old `recent` document remains a bounded migration hint and serialization fence, alongside the legacy timestamp-query hint. Pre-index history is not comprehensively backfilled. `_OrderedTurnstile` reduces bridge work within a job; correctness does not depend on it.

`utils/conversation_continuity.py` owns the gap predicate: an uncovered gap **at least 120 seconds** splits. Both paths measure speech silence. Sync uses the VAD-segment origin through the last word end, exactly as before; no quiet-file coverage expands that interval. Source, device ID and lock state form disjoint partitions. Client conversation IDs can change on reconnect and never partition capture membership; any retained `sync_capture_id` is provenance only. Missing device ID is its own partition, never a wildcard joining two known devices. Live rows with real transcript or photo content may be explicit targets, never automatic bridge donors. Missing targets and empty live stubs use ordinary sync assignment; stubs remain untouched, independent of their status or discarded flag. Encoded transcripts are decoded before testing for content. Existing unattended sync targets are temporal hints, not forced attachments. Shared, photo-bearing or user-curated sync rows also stay intact; they cannot donate content or change identity automatically.

When matches exist, the survivor is the existing row with earliest `started_at`, then smallest ID on a tie. Incoming chunk IDs create records only when nothing matches. Ordinary append keeps its visible ID; genuine bridges retain redirect tombstones. Partition and absolute content converge across permutations, not the survivor ID. Explicit real live targets retain their ID and lifecycle authority; user-deleted targets are never reused. This does not authenticate client provenance. Transcript ranges remain absolute through rebasing; `finished_at` is the last word end; the existing duration helper controls displayed speech duration.

Bridge writes increment survivor and donor `sync_content_revision`. Processors reject deleted rows and stale revisions. `sync_merged_from` persists ancestry with the transcript, so `bridge.py` can replay external effects after a failed attempt. The only completion call is after segment audio persistence in `process_segment`; transactional lifecycle intake has no external cleanup. It reuses merge/delete retraction and audio-copy machinery outside the transaction. `database/sync_bridges.py` checkpoints `sync_bridge_cleaned_revision` on each tombstone with a revision compare-and-set, and later appends skip completed retraction. `sync_bridge_audio_target` tracks the copy destination: later bridges and late donor audio copy without repeating completed retraction. Cleanup/copy/checkpoint failures propagate to the job retry path; concurrent attempts may repeat effects until a receipt commits. Original audio and donor tombstones remain while uploads can finish; deleting the visible conversation also purges its retained sources. In-flight donor audio is recopied when its worker finishes. There is no independent cleanup scheduler: recovery depends on a retried job or later intake. Search-index writes retain their existing best-effort semantics.

## Relevance and remaining differences

Short filler-only speech gets `sync_relevance=review`, remain visible with a deterministic title, and skip enrichment. Subsequent intake reassesses the complete transcript. Unknown content/language stays `keep`; speaker profiles and `is_user` never gate assignment or relevance.

Explicit follow-up outside this change: realtime should reuse conversations across reconnects inside the continuity window and reap empty stubs. Sync leaves live stub lifecycle untouched.

The remaining boundary-policy input difference is timeout configuration: realtime can configure its timeout per session; shipped WALs do not carry that setting, so sync uses the default 120 seconds. Tests replay the in-order realtime speech rule as the reference and require identical sync membership, absolute transcript ranges and extents across arrival permutations, including 119-second joins and >=120-second splits with live stubs present. Sync enrichment remains per finishing job and revision-fenced, not quiescence-debounced. Historical aliases already returned to clients may require a history refresh. Tests model serial commit permutations and replay failures hermetically; Firestore retry contention and live UI acceptance require separate evidence.
