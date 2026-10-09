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
- `processing_trigger.py` owns *why* a conversation is processed. Every caller
  of `process_conversation` (and every finalization job) names a
  `ProcessingTrigger`; its `PROCESSING_MODES` row fixes run-now, reprocess,
  JIT first-open bypass, and relevance policy together. Callers never pass
  mode flags directly.
- `relevance.py` owns the one keep/discard decision. Triggers assess unless
  they are themselves a user action (first open, reprocess, merge).
  Assessment is tiered: user restore (`sync_relevance_user_kept`), then the
  stdlib-only rules in `relevance_rules.py`, then the `conv_discard` model for
  the ambiguous middle; a calendar overlap overrides any discard. The outcome
  is stored as `relevance_decision` (server-only, outside the wire model) and
  counted in `omi_conversation_relevance_decision_total`.
  With `CONVERSATION_RELEVANCE_JEV_ENABLED` (default off) the model tier of a
  transcript-only conversation asks the Jev decision model instead
  (`relevance_jev.py`, gateway lane `omi:auto:jev-decisions`) and discards only
  when P(discard) exceeds `JEV_DISCARD_THRESHOLD`; no answer keeps
  (`decided_by=jev`, `reason=jev_error`). Photos and wake-word invocations keep
  `conv_discard`. The record carries the probability under `jev`. EXP-004 uses
  `relevance_arm(uid, conversation_id)`: a stable per-conversation keep-all
  sample takes precedence over the per-conversation Jev ramp (salt
  `relevance-arm-v2`, range [K,min(100,K+J)); other conversations use nano. Keep-all bypasses only the reached model tier;
  restores/rules/plan gates remain first. Both samples and the shadow receive the same conversation ID, independent
  of account identity; increasing J with K fixed retains existing Jev conversations.
  The UID allowlist is read only with `OMI_ENV_STAGE=dev`; prod declarations
  (including empty bindings) are rejected by the runtime env validator.
  Unset live percentages preserve dev's flag-on=everyone behavior. Production
  stage 2 is live at J=10 after stage 1 soaked 24 h from 2026-10-01 22:46Z,
  with 14 Jev gateway timeouts and no Jev-attributable 5xx. Keep-all K=2
  remains live on all five processing hosts and wins any overlap. Non-keep-all
  conversations outside the Jev range stay on nano; nano remains the large
  control arm, not a separate matched nano-only cohort.
  Owner-flip flags and UID allowlists remain absent.
  `CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT` admits short,
  transcript-only model-tier decisions outside the Jev arm asynchronously, with
  Redis dedupe/daily caps, a bounded queue and text-free 60-day shadow records.
  Live rollout is 1% -> 10% -> 50% -> 100%, with 24 h soak per stage. Abort
  criteria: Jev failures >5%, p95 latency >2x, actual discard rate differing
  from shadow prediction >20% relative, rising empty titles among Jev-kept
  conversations, rising 7-day deletes/restores of Jev-kept/discarded conversations,
  or notes spend per DAU above cap. Discards are recoverable; restoring records
  `sync_relevance_user_kept`. These monitoring gates belong to the coordinator;
  this PR adds no automatic fleet controller. Exact env blocks, provider bindings
  and sync metric visibility limits are in
  `backend/docs/experiments/EXP-004-jev-relevance-owner-ramp.md`.
- `owner_attribution.py` owns typed source-cluster evidence for memory writes.
  A passive memory may be attributed to the account owner only when the
  transcript identifies exactly one owner speaker cluster, keyed by
  `(speaker_id_scope, speaker_id)` so merged conversations cannot collapse
  distinct sources. Speaker resolution (`speaker_resolution.py`, run by
  `process_conversation` before summarization) rewrites resolved segments to
  one `conversation:{id}` scope with one id per voice, so the owner is one
  cluster instead of one per capture chunk. Segment `is_user` labels and model-authored `about=user`
  cannot override that evidence, including for quote promotion. Legacy
  transcripts without cluster IDs fail closed: a `TranscriptSegment` that
  only materialized `speaker_id` from the SPEAKER_00 default is not
  cluster evidence.
  One flagged exception (`MEMORY_OWNER_JEV_FLIP_ENABLED`, default off,
  `owner_jev.py`, universal when enabled — INV-MEM-5 forbids UID cohorts in
  live owner attribution): a candidate capture resolved to a *third party* may be
  re-attributed to the user when Jev's P(owner = user) is at least 0.9. It
  never moves a candidate away from the user or out of `unknown`, and the
  item's `promotion.source_attribution.override` records the probability and
  the pipeline's original subject so the flip can be audited or reverted.
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
  bulkhead, and runs external integrations. For `SERVER_RECOVERY`, a minimal
  structure is a typed failure before persistence. The flagged Cloud Tasks
  worker closes that job on its first occurrence, retaining the transcript as
  a visible completed conversation; provider and parser errors still retry.
  A clear rule-level discard is not a minimal structure: recovery records it
  as an explicit server-recovery discard only after strict transcript decoding,
  so contentless rows never surface. Discard persistence omits the transcript
  fields, preserving the stored blob byte-for-byte. It rechecks protected
  structure, user title, and the restore marker transactionally; a raced edit or
  restore takes the same typed-minimum terminal path, retaining a visible row
  with no new discard decision. Selfheal reports that job as dead-lettered.
  Every terminal that moves a `processing` row into the list (dead-letter, BYOK
  abandonment, orphan recovery) replaces an empty title with
  `deterministic_minimum_title`; the dead-letter also marks a transient failure
  `summary_retryable` (see `database/conversation_finalization_jobs.py`).
- `smart_merge.py` folds a finished pendant conversation into the immediately
  preceding one of the same device partition when Jev says it is the same
  occasion (`CONVERSATION_SMART_MERGE_MODE=off|shadow|merge`, default `merge`; `off`
  is the kill switch and an unrecognized value also means `off`). The
  finalizer calls it behind the fanout claim and before any derived effect;
  `CAPTURE_END` only. `smart_merge_policy.py` holds the pure gates and absorb
  payloads, `smart_merge_state.py` the benchmark question and state (A is always
  one fragment from the survivor's `smart_merge.fragments` ledger, never its
  regenerated summary), and `database/smart_merge.py` the transactions. The
  survivor keeps its id; the donor becomes the sync bridge's redirect tombstone
  (`deleted`/`discarded`/`sync_merged_into`, survivor `sync_merged_from`), so
  existing redirect readers and the deletion purge apply unchanged. The survivor
  is reprocessed once per merge (`ProcessingTrigger.SMART_MERGE`); a retry of a
  donor whose cleanup or refresh failed resumes it before the fanout claim, and a
  failed refresh releases its own invocation lease. Resume first checks the job
  epoch/generation/binding; terminal or stale deliveries do no work. Active refresh
  leases exclude even same-job callers, and a processing receipt prevents a vector
  retry from rerunning the completed bundle. Deferred cleanup remains retryable. An absorb
  requires `refreshed_revision == revision`, so a refresh never persists over a
  newer append. The absorb also advances `sync_content_revision` to fence
  processors that read the old transcript, and refresh persistence checks the
  current lease owner and revision. Custom-STT rows are excluded because their
  processing budget can refuse the required refresh. Decisions are recorded as
  server-only `smart_merge_decision` before the absorb transaction.
  Constants and benchmark provenance live in `config/conversation_smart_merge.py`.
  `CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE` (`off`/`shadow`/`on`, default
  `off`) adds a second gap policy that applies only when both rows carry live
  `external_data` stamps — nonempty `recording_session_id`, nonempty
  `recording_origin_id`, equal origins (session ids name server rollover
  generations and are never compared). The gate then uses the server wall
  clock: `new.created_at - last.finished_at` within `0..MAX_GAP_SECONDS`,
  where `last` is the ledger fragment with the maximum `finished_at`
  (`smart_merge_policy.newest_wallclock_fragment`; `started_at` drifts on
  rollover so it never selects). A newest fragment owned by a donor tombstone
  is fetched as one bounded full row at decision time and re-read inside the
  absorb transaction (reusing the flatten ancestry read when the id is already
  in the union), so a concurrent mutation of origin, finish or status is
  rechecked against the transaction's current row rather than trusted —
  the policy is re-run on that fresh row, so a moved `finished_at` is
  decided on the new value, and only absent or mismatched proof runs the
  exact legacy policy including the speech-gap minimum. Wall-span caps use
  `created_at`/`finished_at`; `wallclock_gap_negative` and
  `wallclock_time_invalid` are the bounded new skip reasons. `shadow` runs the
  corrected evaluation only when the legacy gate skipped a proven pair — one
  extra Jev question with corrected timing, one bounded
  `smart_merge_wallclock_shadow` log line and counter, no writes. Deployment
  defaults to `shadow` on all six smart-merge hosts in dev and prod
  (`backend`, `backend-sync`, `backend-sync-backfill`,
  `backend-integration`, `backend-listen`, `pusher`). Timestamp
  computation is unchanged: `started_at`, transcript rebasing and stored
  ledger entries keep the drifted speech axis; only the decision record's
  `gap_seconds` (wall) / `speech_gap_seconds` (`None`) and the Jev state's
  endpoint starts (replaced by `created_at`) reflect wall time.
- `duplicate_capture.py` owns the advisory cross-source overlap policy (#3244).
  After durable finalization, it links the shorter completed capture using
  `external_data.duplicate_capture_of` plus structured overlap evidence. The
  database transaction rechecks both captures; discard and content stay independent.
- `shared_speech.py` confirms a window match from content (word-trigram containment of
  the smaller transcript). Confirmed pairs join a capture group through
  `database/capture_groups.py`, the sole writer of `capture_group`; processing writes
  strip it. Grouping is presentation metadata; content and derived work stay per capture.
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

EXP-004 owner measurement (`MEMORY_OWNER_JEV_SHADOW_PERCENT`) asks only grounded
third-party candidates not scored by the live flip path, including those beyond
its eight-candidate budget. It records the full owner distribution without
changing capture output. Both shadows share `jev_shadow.py` admission/worker
primitives and persist only numeric/enum/identifier metadata through
`database/jev_shadow.py`; Redis unavailable fails closed before vendor egress.
Their lazy ten-worker `jev-shadow` executor is isolated from foreground LLM
work. Admission owns a bounded Redis client per attempt; vendor calls and
retry-free Firestore writes consume only the remaining 2.5-second task budget.

Owner shadows gather the full eligible batch, hash conversation ID + candidate
full scoring SHA256 against the lane percentage, deduplicate identical identities and select the
eight lowest before submission. The owner bulkhead has eight slots (relevance
two); per-conversation cap and cross-conversation saturation losses remain
`dropped` coverage. Records include original zero-based `candidate_index` and
deduplicated pre-percentage/pre-cap `eligible_count`, both integers. Owner identities
include candidate text, complete speaker-labelled scoring state, question user
name and pipeline subject kind/entity ID; same text with different evidence is
measured separately. Only hashes and numeric/enum metadata are persisted. Dev's four live-flag hosts pin
`MEMORY_OWNER_JEV_FLIP_PERCENT=0` to avoid starving the shadow. This control is
universal: only 100 permits the flag; intermediate/invalid values disable it.
Either malformed relevance arm percentage resolves everyone to nano.

Firestore's deadline race bounds waiting; an already-started commit can persist
later. Deterministic IDs include lane, conversation, scoring identity hash (text
hash for relevance) and question
version. Transactional first-write-wins preserves scores and retention timestamps.
Readouts include valid late writes once per (uid, document ID), independently of
attempt `timeout`/`ok` counters. Account deletion remains transactionally fenced. Concurrent commit losers
(the SDK wrapped-Aborted outcome) count as `deduped`, never scoring failures.

The production shadow percentages are 100 (all five processing hosts). The
production keep-all arm is live at 2 (started
2026-10-01): a stable 2% of ambiguous model-tier conversations, chosen by
conversation ID, are kept regardless of nano and record nano's would-be verdict;
rollback is percent 0 and a redeploy. Jev relevance stage 2 started 2026-10-03
at J=10 on the same five hosts, after stage 1 soaked 24 h from 2026-10-01
22:46Z with 14 Jev gateway timeouts and no Jev-attributable 5xx. Keep-all takes
precedence; the independent Jev bucket range is [2,12), and non-keep-all
conversations outside it stay on nano. The nano remainder is the large control
arm, but not a separate matched nano-only cohort. Owner-flip flags and UID
allowlists remain absent; caps stay unchanged.
The coordinator enabled `jev_shadow.expire_at` TTL
in `based-hardware` on 2026-10-01 and verified ACTIVE before the flip. Sync hosts have no exporter;
readouts must distinguish their records from scraped attempt/latency coverage.
