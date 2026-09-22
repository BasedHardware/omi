# Sync utilities

This package owns uploaded-audio sync admission, decoding, transcription orchestration, persistence fencing, and playback reconstruction.

## Boundaries

- `pipeline.py` coordinates job/run leases, segment processing, persistence fences, and terminal outcomes. `assignment_errors.py` distinguishes terminal user authority from corrupt/mismatched intake.
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

`utils/conversation_continuity.py` owns the gap predicate: an uncovered gap **at least 120 seconds** splits. Both paths measure speech silence. Sync uses the VAD-segment origin through the last word end, exactly as before; no quiet-file coverage expands that interval. Source, device ID and lock state form disjoint partitions. Any retained `sync_capture_id` is provenance only; an explicit existing target is authoritative independently of temporal assignment. Missing device ID is its own partition, never a wildcard joining two known devices. Every provenance-compatible, non-deleted explicit target retains its ID, including an empty live record or an existing sync row. Fresh admission can verify server capture proof before any live transcript exists; emptiness is not evidence to reject that target. Missing or tombstoned explicit targets use ordinary temporal assignment, subject to independent retry-lineage deletion fences. Timestamp hints never adopt live rows, regardless of content, status or discarded flag. Explicit live targets acquire `sync_live_target` and remain excluded from automatic bridges after sync adds content and revisions. Shared, photo-bearing or user-curated sync rows also stay intact; they cannot donate content or change identity automatically.

Without an authoritative explicit target, when matches exist the survivor is the existing row with earliest `started_at`, then smallest ID on a tie. Incoming chunk IDs create records only when nothing matches. Ordinary append keeps its visible ID; genuine bridges retain redirect tombstones. For unattended temporal intake, partition and absolute content converge across permutations, not the survivor ID. Explicit targets retain their ID and lifecycle authority; user-deleted targets are never reused. This does not authenticate client provenance. Transcript ranges remain absolute through rebasing; `finished_at` is the last word end; the existing duration helper controls displayed speech duration.

Bridge writes increment survivor and donor `sync_content_revision`. Processors reject deleted rows and stale revisions. `sync_merged_from` persists ancestry with the transcript, so `bridge.py` can replay external effects after a failed attempt. The only completion call is after segment audio persistence in `process_segment`; transactional lifecycle intake has no external cleanup. It calls the public `retract_sync_bridge_source` and `copy_sync_bridge_audio` seams in `merge_conversations.py`; those fix retention and strict-copy policy while keeping the general merge/delete machinery private. `database/sync_bridges.py` checkpoints `sync_bridge_cleaned_revision` on each tombstone with a revision compare-and-set, and later appends skip completed retraction. `sync_bridge_audio_target` tracks the copy destination: later bridges and late donor audio copy without repeating completed retraction. Donor retraction does not take the exclusive per-account destructive gate; if that gate is already held, retraction is deferred (logged `event=sync_bridge outcome=deferred`) and retried on the next append via the missing receipt. Copy and checkpoint failures still propagate to the job retry path; concurrent attempts may repeat effects until a receipt commits. Original audio and donor tombstones remain while uploads can finish; user/source deletion purges retained sources through `delete_conversation_with_sync_sources`, called by the deletion service and developer delete endpoint; the raw database hard-delete primitive does no external orchestration. In-flight donor audio is recopied when its worker finishes; the previous copy receipt is cleared first, so failed late copying remains pending on retry without a transient source hint. There is no independent cleanup scheduler: recovery depends on a retried job or later intake. Search-index writes retain their existing best-effort semantics.

## Relevance and remaining differences

Short filler-only speech gets `sync_relevance=review` and skips enrichment. Uncurated completed review fragments are effectively discarded: hidden from default lists/search, retained with their transcript/audio, and recoverable through Show discarded. New intake persists `discarded=True`; read projection applies the same policy to legacy review rows without a destructive backfill. Explicit restoration sets `sync_relevance_user_kept` so later intake honors that choice. Curated, shared, photo-bearing, live-target, and already enriched records are protected. Duration alone never discards meaningful speech. Subsequent intake reassesses the complete transcript. Unknown content/language stays `keep`; speaker profiles and `is_user` never gate assignment or relevance.

Known limitation: WALs carrying different existing live target IDs can remain separate even during one continuous recording. Sync never bridges those live-owned targets because an open socket may still write to them; partial-flap intake does not guarantee partition parity. Realtime now remembers same-origin continuations inside the continuity window and reaps expired empty generations on reconnect. This prevents one source of new target proliferation; it does not redirect historical distinct explicit live targets. A lineage migration remains separate.

The shared arithmetic does not unify the observed clocks: live finished_at is currently callback wall time, while sync uses VAD/word ends. Another boundary-policy input difference is timeout configuration: realtime can configure its timeout per session; shipped WALs do not carry that setting, so sync uses the default 120 seconds. Tests replay the in-order realtime speech rule as the reference and require identical sync membership, absolute transcript ranges and extents across arrival permutations for temporal intake, including 119-second joins and >=120-second splits with hint-only live stubs and missing target IDs present. Sync enrichment remains per finishing job and revision-fenced, not quiescence-debounced. Historical aliases already returned to clients may require a history refresh. Tests model serial commit permutations and replay failures hermetically; Firestore retry contention and live UI acceptance require separate evidence.

## Assignment outcomes

Labeled non-target donors are excluded before extending the capture interval. A labeled
row may remain the survivor for temporal appends, but never donate its receipt into
another speaker namespace. Retargeting a labeled retry anchor is permanent supersession.

Deleted anchors, deleted redirect lineage and user-managed or labeled retargeted retry anchors raise
`SyncAssignmentSuperseded`. `process_segment` consumes them quietly with no error,
content usage or response IDs. It returns false, letting sibling segments proceed;
a zero-error job commits the content-completion ledger before publishing completed
(inline and Cloud Tasks). The bounded log is `sync_assignment outcome=superseded`;
this does not masquerade as speech silence. Provenance mismatches and redirect cycles
raise `SyncAssignmentConflict` and remain loud retryable upstream errors under the
existing job error taxonomy. Copy/checkpoint failures also retain retry behavior.
Donor retraction that collides with the account destructive-operation gate is
deferred and converges on a later append; it does not fail the accepted chunk.

## Speaker identity

Speaker IDs are conversation-local. Each independently transcribed WAL chunk
carries a retry-stable content scope (legacy direct intake uses capture time).
After duplicate removal, the transaction hydrates the surviving conversation's
allocator and allocates incoming and donor identities. Legacy donors receive a
stable conversation/speaker scope. Provider labels and recognized person IDs are
preserved; equal provider numbers never establish that two voices are the same.
