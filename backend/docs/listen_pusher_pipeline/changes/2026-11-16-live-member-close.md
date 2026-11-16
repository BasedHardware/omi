# Live members no longer block closed-episode summaries

`EPISODE_LIVE_MEMBER_CLOSE_ENABLED` defaults on. Active batch-live captures use
their stored capture start, rather than their arrival clock, to open or join the
live episode. A silence boundary is half-open: a start at or after the boundary
belongs to the successor. Membership, reverse links, navigation and the recorded
timeline fence commit together. A stale gap close cannot erase a newer activity
receipt.

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
image. Compare end-to-summary timing on synthetic/consenting-owner captures,
without counting `composed_at` as proof of Home paint.

`omi_episode_live_member_total{outcome="rehomed"}` counts successful repair
commits; `outcome="excluded_readiness"` counts readiness observations, including
repeat reads. Neither is a unique affected-user count. Observe these alongside
`omi_episode_compose_total{outcome="waiting"}` and compose errors/conflicts;
legacy waiting outcomes have no blocker label and cannot establish historical
attribution. No metric contains account or recording identifiers.

Rollback: set `EPISODE_LIVE_MEMBER_CLOSE_ENABLED=false` on every affected host.
It stops new rehomes/exclusions and restores legacy placement/readiness; it does
not undo already committed ownership. No data migration or production write
script is part of this change. Custody acknowledgements, audio barriers, usage,
STT admission and billing remain under their existing authorities.
