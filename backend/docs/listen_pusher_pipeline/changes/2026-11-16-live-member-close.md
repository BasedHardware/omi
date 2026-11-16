# Live members no longer block closed-episode summaries

`EPISODE_LIVE_MEMBER_CLOSE_ENABLED` defaults on. Active batch-live captures use
their stored capture start, rather than their arrival clock, to open or join the
live episode. A silence boundary is half-open: a start at or after the boundary
belongs to the successor. Membership, reverse links, navigation and the recorded
timeline fence commit together. Rehoming requires corroborating finite
`server_batch_audio_start`, stored `started_at` and canonical `recorded_start`
with trusted provenance (`live_capture`, `frame` or `device`). Their interval
must be at most five seconds wide, no source may exceed transaction server time
by more than five seconds, and every source must be at or after the boundary.
A first admission has no owner to change and shares main's existing selector:
finite `server_batch_audio_start`, then stored `started_at`, then `created_at`.
The selector is shared with batch admission, without additional trust or future
refusals on initial placement. No known start keeps admission's existing skip
behavior. Existing membership changes always require all three trusted clocks.
Missing/untrusted clocks, wider disagreements, and even a small disagreement
across the boundary retain existing ownership. Finished-subset readiness still
unblocks that episode. A stale gap close cannot erase a newer activity
receipt. Rotation drops unresolved provisional items, clears pending boundaries,
and schedules the closed summary after commit. Rehoming preserves the member's
recovered classification as well as its provisional state and consumption offsets.

The normal composer lazily repairs legacy post-gap active members into a live
successor. It keeps the old membership when placement is uncertain (including a
newer, nonoverlapping current episode or a full read budget). No recording is
deleted or merged. An active member that began inside the old episode stays
linked, but is excluded from its summary inputs and readiness. Finished members
compose immediately through the existing settle, lease and paid-work contracts.
The member is included again after finish, through finalize/read recovery.

A summary write checks that an excluded member is still capturing, rather than
comparing its audio-append revision. Finish, hide, relevance-discard and lock
changes still reject stale writes. Home preparation certifies the finished
summary independently of the excluded member's continuing audio appends; it
rechecks that the member is still capturing. The existing phone aggregation
continues to enforce one processing row. No phone code changes.

Roll the same image across `backend`, `backend-listen`, `pusher`, `backend-sync`,
`backend-sync-backfill`, and their conversation-finalization executors. Quality
lead owns the rollout: validate a no-traffic candidate, then a small serving
slice, then all of those services in the same release window after clean
compose-error/timeline-conflict signals. Do not leave composer hosts on an old
image. `EPISODE_RECORDED_TIME_ENABLED=false` also stops the placement/repair
writer; finished-subset readiness remains independently protected by the live-member
switch. Repair re-reads member metadata and validates prospective moves inside
a transaction; retained pre-boundary members return before the candidate query.
Watch Firestore read rates alongside compose/errors during the serving ramp.
Compare end-to-summary timing on synthetic/consenting-owner captures,
without counting `composed_at` as proof of Home paint.

`omi_episode_live_member_total{outcome="rehomed"}` counts successful repair
commits; `outcome="excluded_readiness"` counts readiness observations, including
repeat reads. `omi_episode_live_member_clock_refusal_total{reason}` counts
retained memberships with closed reasons `missing`, `untrusted`, `future`, or
`disagreement` (including boundary-straddling intervals). Counters are emitted
after the ownership transaction returns, so transaction retries do not duplicate
a refusal observation. Neither counter is a unique affected-user count. Observe these alongside
`omi_episode_compose_total{outcome="waiting"}` and compose errors/conflicts;
legacy waiting outcomes have no blocker label and cannot establish historical
attribution. No metric contains account or recording identifiers.

Rollback: set `EPISODE_LIVE_MEMBER_CLOSE_ENABLED=false` on every affected host.
It stops new rehomes/exclusions and restores legacy placement/readiness; it does
not undo already committed ownership. No data migration or production write
script is part of this change. Custody acknowledgements, audio barriers, usage,
STT admission and billing remain under their existing authorities.
