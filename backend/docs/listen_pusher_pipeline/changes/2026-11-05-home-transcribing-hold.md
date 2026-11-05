# Home transcription presentation gate, phase 1

Desktop server-batch completion intentionally precedes transcript replacement.
Home could therefore expose a completed raw recording without a transcript or
title, then reshape it when batch results arrived. Phase 1 preserves that
ordering (lead2 ruling `04d9b7`; early completion ruling `f1e35a`) and changes
only presentation. The one-writer completion/finalization redesign is phase 2.

The completion CAS stamps `home_transcription_pending_at` and
`home_transcription_deadline_at` atomically with `status=completed`. A rejected
CAS writes neither clock; retries of the completed row cannot renew them.
`HOME_TRANSCRIPTION_DEADLINE_SECONDS` defaults to **7200 seconds**, matching the
existing batch timeliness SLA and Episodes transcription deadline. Invalid,
blank or nonpositive values use 7200. A setting change affects new completions,
never an existing row's deadline.

`HOME_TRANSCRIPTION_PRESENTATION_GATE` defaults **on**. A stamped, batch-owned,
completed row with no transcript, user title or structured title, and no batch
projection receipt, renders `processing` / `Transcribing…` at the main list,
main detail, shared/developer detail, search, folder/developer lists and star
replacement API exits. Developer and MCP schemas
use the same title mapping (their existing wire models have no status field). Indexed main lists
carry the deadline and batch projection receipt without downloading transcripts.
`has_content` is not a transcription receipt: the raw audio writer sets it too.
The labels share the Episodes Home mapping. Expiry (inclusive), dead letter or
upload failure changes the title to `Couldn't transcribe`. On conversation APIs
this recovery exit uses `completed`, so the ordinary failed-status filter cannot
hide it; Episodes retains its existing `failed` member wire mapping.

Home list/detail opt into the stamped-row exception in the shared visibility
predicate, including after expiry. Job readers keep the default settling hold. Deletion, discard, duplicate and bridge
visibility fences remain authoritative. No read writes status, custody, title or
a deadline. Shared database hydration remains authoritative for lifecycle jobs;
`replace_record`, `SERVER_RECOVERY`, `CLIENT_FINALIZE`, orphan sweep and the
finalizer's reservation/completion ordering are unchanged. Existing unstamped
rows are unchanged; this PR does not backfill them.

Writer-version conditional list responses are disabled while this lever is on:
deadline decay changes a response even without a write/version bump. Otherwise
a 304 could freeze `Transcribing…` indefinitely. Developer conversation list body caching is also bypassed while enabled.
Turning the lever off restores the prior conditional-list behavior as well as stored conversation status/title.

Rollback: set `HOME_TRANSCRIPTION_PRESENTATION_GATE=off` on the serving services;
there is no data migration to undo. Clock stamping remains enabled so a later
re-enable uses the original durable deadline. Dev/prod runtime overlays declare
the lever on and the deadline 7200 for the main API/finalization services;
staging inherits prod. The separate chat-oriented desktop-backend does not mount conversation routes
and keeps its existing deployment manifest. No environment was
deployed by this change.

`visibility:transcribing_hold` declares its atomic entry clocks and reader-enforced
decay exit in the lifecycle table. **Declared gaps:** no dedicated authoritative
presentation dwell/stock gauge or alert. Both are explicit strict-xfail clauses,
tracked by ANX `card:homegate` / `card:lcinv-lifecycle-invariants`; the existing
batch timeliness alarm is not claimed as a measurement of this presentation
state. This phase adds no metric producer or alert deployment.

Verification covers the hermetic API wire path, CAS fences/nonrenewal, indexed
visibility, populated rows, lever rollback and unchanged batch/finalizer replays.
No production cohort, frequency of flash, vendor latency distribution, API read
cost, deployed flag state or real-device rendering was measured. No GCP access,
merge or deploy is part of this PR.

Contract: [Home transcription presentation](../../listen_pusher_pipeline.mdx#home-transcription-presentation).

## Scope audit

The supplied scope report was checked against `origin/main` at
`cba5d6e47d2991dcbc9d5d96e68318de2f088920`: completion remains at
`utils/conversations/lifecycle.py:337-354`, with the caller at
`utils/conversations/finalizer.py:275-305`; list visibility is
`database/conversations.py:905-925`; Episodes labels/deadline are at
`utils/episodes/home_read.py:305-320` and
`database/episode_batch_pending.py:26-38`. `replace_record` still requires
completed storage (`utils/batch_pipeline/live_projection.py:27-28`).

Of the cited source blobs, `database/batch_pipeline_projection.py` has advanced
since the report's `015fe4f` base: `ProjectionStore.mark_enrichment` now handles
rollover output IDs, still committing the enrichment obligation/receipt before
its wake (`:248-310`). It is untouched here. The report's
`routers/websocket.py` path does not exist on this base; its tentative websocket
claim is unverified and is not an acceptance claim for this change. Client
fallback behavior is at `app/lib/utils/conversations/conversation_title.dart:47-60`.

## Consumer review

Required Grok review found that macOS maps all `processing` wire rows to the
summary-progress UI, discarding their supplied title and offering Reprocess at
600 seconds. The narrow client projection now honors the server's exact
`Transcribing…` title for an empty, non-deferred processing row, retaining the
wire status while bypassing the summary-stall affordance. Ordinary processing,
deferred, locked and populated rows retain their existing interpretation. This
requires the macOS source change to ship as well; no installed artifact or live
client rollout was measured here. The regression exercises the production model, detail banner eligibility and
summary empty-state copy. Detail refetch still follows the wire processing status;
the transcription hold cannot offer summary-stall Reprocess or claim the
transcript is already saved.

The review also caught the shared-visibility exception reaching jobs, and missing
list/star projections. Home reads now opt in explicitly; authoritative job
visibility is unchanged. Search, folder, developer and MCP list exits share the
presentation primitive and select its batch receipt fields before transcript
omission. Speaker-assignment mutations require existing segments, so an empty
batch placeholder cannot enter that path; its resulting content is outside the
hold predicate.

## Concurrent atomic completion integration

While this lane was under validation, #24702 moved the completion CAS into
`database/conversation_finalization_jobs.py:_complete_server_batch_capture_txn`.
The deadline clocks now commit with that primitive's conversation-and-job
terminal write. Completed replay, stale generation/lease and privacy fences
return before the stamp; a successful replay cannot renew the deadline. The
lifecycle wrapper and finalizer retain the new upstream protocol byte-for-byte.
The state-table entry and reviewed writer inventory name this actual writer.
Atomic completion and both recovery/finalize trigger replays are covered without
reintroducing split terminal writes or changing completed-before-STT ordering.

The phase-1 review also traced the developer transcript-inclusive list, integration
list, and hosted MCP tools. These product readers opt into the same stamped-row
visibility exception before pagination and apply the shared pending/overdue title
projection before serialization. MCP bounded projections include the deadline and
batch receipt metadata without exposing those fields in tool responses. No worker
or finalizer reader is opted into presentation state.

Follow-ups remain separate: broad main-list 304 bypass has an unmeasured read-cost
impact, and historical rows without a stamped deadline are not backfilled. Neither
follow-up changes the default-on presentation gate or its rollback contract.
