# Home processing ownership (dark)

A live episode owns its Home members. The Flutter fix always hides membership
before skipping a row owned by active Listening and excludes the same members from local processing
insertion. Closed episodes still composing keep their Processing row.

Backend switches, all evaluated per call and both defaulting to false. The behavior below applies when enabled:

- `HOME_PROCESSING_OWNERSHIP_ENABLED=true`: read-only Home/pending-work suppression
  of live members and jobs whose full target set is already represented. Partially
  represented and unknown-target jobs remain visible. No job is retired by hiding it.
  Live suppression requires an admitted request channel and `X-Omi-Home-Ownership: 1`;
  older clients and date-filtered Home lists retain their recordings. Writer-lease
  probes remain unfiltered. Live-state-dependent lists bypass version caching.
- `HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED=true`: automatic notes for a linked
  live member wait for episode close. Durable finalization yields without spending
  a processing attempt; enrichment uses its existing deferred settlement.
  An authenticated recording detail read grants that recording a five-minute
  escalation lease and wakes its existing durable enrichment obligation. Explicit
  reprocess and finalize retain their intent. Transcription and custody continue.
- `HOME_PROCESSING_OWNERSHIP_UIDS` optionally restricts both switches to named
  accounts. Empty allows all only when the respective switch is true.

The notes switch narrows Phase 2's watched-Home behavior: a Home/watch lease or
owner-wide promotion cannot override it. Recording detail can. Phase 2 retains
its own seal, patient deadline, close and composer controls. The finalizer hook is
after `_episode_at_finalization_start` and batch registration, so automatic boundary closure cannot wait on notes.
Never enable this switch until both owners review the combined scheduling policy.

`create_sync_job` persists supplied `recording_ids` and `target_conversation_id`
with its original Redis TTL before any transcript result. Live WAL upload already
carries `conversationId` and `recordingSessionId`. Session-only uploads can still
have an unknown conversation until worker-side assignment; this PR does not infer
that relationship or change the upload contract. This limitation was reported to
the coordinator before implementing supplied-ID persistence. Pending responses
use admission targets only with ownership enabled, and report `recording_count`
from distinct recording IDs (legacy fallback: distinct conversation IDs, then one
unknown recording), never from WAL file/segment counts. Listed jobs share a
distinct recording-ID census, so chunk jobs for the same recording count once;
partial overlap contributes only newly represented recordings. Jobs without any
recording or conversation identity remain separate. Raw writer-lease readers
retain every job.

`omi_episode_home_attach_gap_total` counts read observations of missing membership
for recordings wholly inside the current live ownership window. Repeated reads
count again; it is not a unique-recording or failed-attempt counter. Each observation
logs `event=episode_attach_gap outcome=home_suppressed`. Another explicit episode
owner wins. Temporal hiding does not attach, move or delete a recording. Filtered
lists and detail reads preserve access; ordinary attachment repair remains owner.

## Ramp and rollback

No merge, deployment, production flag or IAM change is part of this PR. The project
coordinator owns expansion; the Infra Rollout Coordinator alone applies runtime
changes. Within 48 hours of merge, run staging fixtures with both flags off, then
on; verify live overlap, attach-gap telemetry, detail escalation, and close-to-notes.
Next enable the named internal allowlist for 24 hours, then 25 named beta accounts
for 24 hours. The coordinator reviews each clean receipt within 48 hours and either
expands to all episode-capable accounts or records a dated hold by 2026-11-21.

Require zero duplicate live Home rows, no missing closed/unowned recordings,
no automatic live-member notes without detail intent, no spent retry budget on
settlement waits, and no regression of transcript/custody completion or oldest
notes debt. Attach-gap observations must be investigated before expanding. Verify
close/compose progress and detail readiness against the Phase 2 owner before
activating the notes flag; missing telemetry blocks expansion.

Rollback: set both backend switches false. Existing durable obligations resume
ordinary processing on their next wake; all raw data remains unchanged. Revert the
two Flutter projection changes to roll back the app fix if necessary. Additive job
metadata expires with the existing TTL and requires no migration or backfill.
