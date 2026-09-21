# Conversation utilities

Shared conversation-domain helpers used by API routes, Pusher, sync workers,
and background processing.

## Boundaries

- `live_continuation.py` coordinates durable reconnect admission through
  `database/listen_continuations.py`. The original recording binding remains
  immutable; its continuation metadata is adopted transactionally. Resume
  requires the same source/device and an unlocked, nondeleted in-progress row
  inside the shared continuity window. Expired empty and unexposed losing
  generations use lifecycle's codec-aware transactional deletion; content,
  lock, tombstone and sync revision prevent deletion.

- `factory.py`, `location.py`, `search.py`, and `transcript_chunks.py` provide
  serialization, lookup, and read-model helpers; callers retain ownership of
  request authentication and response shaping.
- `process_conversation.py` is the synchronous enrichment coordinator. It
  persists the completed conversation and delegates expensive child work to the
  named executor lanes. Custom-STT conversations skip managed-STT credits but
  still consult `should_skip_omi_paid_postprocessing` before Omi-paid
  structuring, summary, and memory work (#7690). That gate sits after the
  unpaid desktop on-device / `store_projection` path (#14513) so it cannot
  strip a local summary.
- `owner_attribution.py` owns typed source-cluster evidence for memory writes.
  A passive memory may be attributed to the account owner only when the
  transcript identifies exactly one owner speaker cluster, keyed by
  `(speaker_id_scope, speaker_id)` so merged conversations cannot collapse
  distinct sources. Segment `is_user` labels and model-authored `about=user`
  cannot override that evidence, including for quote promotion. Legacy
  transcripts without cluster IDs fail closed: a `TranscriptSegment` that
  only materialized `speaker_id` from the SPEAKER_00 default is not
  cluster evidence.
  `transcript_for_llm.memory_transcript_from_segments` is the memory-only
  renderer: when owner evidence is untrusted it suppresses owner names and
  prefixes an explicit UNTRUSTED header. Summary and action-item rendering keep
  their existing presentation.
- `wake_word.py` owns the pure, end-of-conversation matcher and trusted inline
  prompt marker. It has no realtime state, I/O, or speaker-identity gate. The
  independent invocation classifier lives in `utils/llm/`; task-intelligence
  capture owns the conjunction gate that consumes its validated verdicts.
- `finalizer.py` is the durable handoff boundary for a persisted conversation.
  A caller must have already acquired a finalization-job lease before invoking
  it; it loads the conversation, performs enrichment through the postprocess
  bulkhead, and runs external integrations.
- `duplicate_capture.py` owns the advisory cross-source overlap policy (#3244).
  After durable finalization, it links the shorter completed capture using
  `external_data.duplicate_capture_of` plus structured overlap evidence. The
  database transaction rechecks both captures; discard and content stay independent.
- `meeting_treatment.py` owns the post-capture meeting policy. It uses durable
  conversation timestamps plus the union of transcribed-speech intervals, so
  dual microphone/system-audio transcripts cannot double-count speech.
- `duration.py` owns the single conversation-duration rule shared with the
  Flutter and macOS clients: the transcript span (largest validated segment
  `end`), falling back to the wall window when no segment survives validation —
  whether the record is transcript-free or its segments are all malformed
  (the malformed-doc branch records a fallback so ops can see the degradation).
  `started_at` is the streaming-session origin, so no caller may recompute
  `finished_at - started_at` as a user-visible or policy duration.

- `overview_markdown.py` renders notes-v2 `structured.overview` markdown to a
  closed HTML subset for the share-email body (headings, lists, emphasis,
  `http(s)` links; every text node escaped).
- `meeting_receipt.py` is the sole writer of the final meeting verdict. It
  records reason and measured inputs on the finalization job, projects the
  verdict to the conversation, and attaches the deterministic Chat intent.
- `typesense_index.py` owns the first-party Typesense projection of the
  durable conversation store. It is called fail-open from the conversation
  write/delete choke points (`database/conversations.py` durable mutations,
  `lifecycle.delete_empty_recording_conversation`, and the account-deletion
  purge), never from routers. Dual-writes on top of the still-installed
  Firebase extension `firestore-typesense-conversations`; the extension is
  removed only after this writer has baked (see the module runbook note).
- The old orphaned WAV retranscription util (`postprocess_conversation.py`) was
  removed: the historical Flutter upload (`memoryPostProcessing`) and
  `POST /v1/memories/{id}/post-processing` router were removed and nothing
  imported the util. (Historical note: short-audio cancels were caused by the
  old client stripping `quietSecondsForMemoryCreation` (120s) from the WAV
  before upload, not by backend truncation.)
- Route- or worker-specific ownership, retries, queues, and leases belong
  outside this package: `database/conversation_finalization_jobs.py`,
  `services/conversation_finalization.py`, and their callers own those states.

## Data and credential safety

This package receives persisted conversation data only. Request-scoped BYOK
context may be propagated by a live Pusher caller into `finalizer.py`, but it
must never be written here, passed to durable task payloads, or logged.

Sync lifecycle intake computes unattended speech components transactionally. A
compatible, non-deleted explicit target keeps its ID even when empty; timestamp
hints never adopt live rows. Explicit live targets remain excluded from automatic
bridges after sync appends. Different existing reconnect targets may therefore
remain separate until realtime reuses its in-progress conversation on reconnect. The pipeline
replays bridge effects once, after audio persistence, through existing merge
retraction/copy helpers; tombstone revision receipts skip completed cleanup. Retained donor
redirects preserve late audio. `merge_conversations.delete_conversation_with_sync_sources`
owns retained-source purging for user/source deletion, called by the frame-evidence
service and developer delete endpoint. Raw DB deletion and new-target rollback do
not orchestrate external cleanup. The shared gap
predicate lives in `utils/conversation_continuity.py`; both paths supply speech
silence (sync uses the default timeout; realtime can configure it per session). See `utils/sync/ARCHITECTURE.md`.
