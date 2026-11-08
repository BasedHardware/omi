# Home processing ownership (default on)

A live episode owns its Home members. The Flutter fix always hides membership
before skipping a row owned by active Listening and excludes the same members from local processing
insertion. Closed episodes still composing keep their Processing row.

Both backend switches default to true and are evaluated per call. Each is an independent
kill switch: an explicit false disables that behavior. Env overrides remain supported.
The Flutter rendering fix and its `X-Omi-Home-Ownership: 1` capability header are always on;
the app does not read these server environment switches.

- `HOME_PROCESSING_OWNERSHIP_ENABLED=true`: read-only Home/pending-work suppression
  of live members and jobs whose full target set is already represented. Partially
  represented and unknown-target jobs remain visible. No job is retired by hiding it.
  Live conversation-list suppression requires an admitted request channel,
  `X-Omi-Home-Ownership: 1`, and the current live episode ID echoed in a valid
  `X-Omi-Home-Episode-Ids` pair. Missing or mismatched echoes keep recordings visible;
  older clients and date-filtered Home lists retain their recordings. Writer-lease
  probes remain unfiltered. Live-state-dependent lists bypass version caching.
- `HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED=true`: automatic notes for a linked
  live member wait for episode close. Durable finalization yields without spending
  a processing attempt; enrichment uses its existing deferred settlement.
  An authenticated recording detail read with `X-Omi-Recording-Detail: 1` grants that recording a 70-minute
  escalation lease (the one-hour maximum hold plus a quiet-window delivery margin) and wakes its existing durable enrichment obligation. Home lifecycle
  probes omit this explicit-open header and cannot escalate notes. Explicit
  reprocess and finalize retain their intent. Transcription and custody continue.
- `HOME_PROCESSING_OWNERSHIP_UIDS` optionally restricts both switches to named
  accounts. Empty allows all only when the respective switch is true.

The notes switch narrows Phase 2's watched-Home behavior: a Home/watch lease or
owner-wide promotion cannot override it. Recording detail can. Phase 2 retains
its own seal, patient deadline, close and composer controls. The finalizer hook is
after `_episode_at_finalization_start` and batch registration, so automatic boundary closure cannot wait on notes.
Both switches ship on by default per David's 2026-11-07 ruling, including the
closed-member notes gate. Review the combined scheduling policy with Phase 2's owner
using the verification below.

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

## Default-on verification and rollback

This PR sets the code defaults on for all admitted episode-capable accounts; no
staged allowlist expansion is required. Existing explicit false env values still
turn the respective behavior off and must be accounted for by the Infra Rollout
Coordinator when shipping. No merge, deployment, production flag or IAM change
is part of this PR. Only the Infra Rollout Coordinator applies runtime changes.

Verify staging fixtures with both flags unset, then explicitly false: live overlap,
attach-gap telemetry, detail escalation, and close-to-notes. Require zero duplicate
live Home rows, no missing closed/unowned recordings, no automatic live-member
notes without detail intent, no spent retry budget on settlement waits, and no
regression of transcript/custody completion or oldest notes debt. Investigate
attach-gap observations. Verify close/compose progress and detail readiness with
Phase 2's owner. Missing telemetry or regressions require investigation and use
of the applicable kill switch.

Rollback: set both backend switches false. Existing durable obligations resume
ordinary processing on their next wake; all raw data remains unchanged. Revert the
two Flutter projection changes to roll back the app fix if necessary. Additive job
metadata expires with the existing TTL and requires no migration or backfill.

Live list omissions require exact client-held episode/member pairs, including
for current live membership and time-overlap ownership. Newly attached or
unacknowledged members remain visible until fetched. All acknowledged omissions
are named in `X-Omi-Home-Suppressed-Ids` for local source restoration. The early
finalizer notes gate also bypasses empty transcripts, including photo-only rows.
