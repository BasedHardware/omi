# F join marker retries a lost compare-and-swap

[PR #24974](https://github.com/BasedHardware/omi/pull/24974) changes how a live F join writes its `pending_boundary` marker.

The marker is written by `mark_pending` in `utils/episodes/f_join.py`, in a second transaction after the recorded attach. It used the `state_version` from attach time. A live episode is rewritten on every moment, so that version was usually stale, and the first `EpisodeConflict` silently fell back to the time-only join with `reason=other`. From 2026-11-08 06:29Z (F at 100%) to 2026-11-09 07:45Z, all 78 pusher attempts fell back and none reached a Jev decision. Rebuilding `pending_boundary` from the stale copy could also drop a concurrent writer's marker.

Now, after a lost compare-and-swap, `mark_pending` re-reads the episode and retries at the fresh version. It makes `MARK_PENDING_ATTEMPTS` (3) attempts in all, and retries only while the join still stands: the episode is live, the conversation is still a member, and the conversation is not already marked. Each retry merges into the fresh `pending_boundary`. When it gives up, it records `f_pending_conflict`, falls back as before, and logs `event=episode_f_join outcome=pending_conflict reason=<conflict> attempts=<n>`.

Unchanged: rollout percentage, kill switches, the attach itself, settlement, the fallback path and its reasons, and every non-conflict error path. A conflict caused by `current_episode_changed` is not fixed by a retry; the new log line identifies that case for a follow-up.

Verification: `pytest tests/unit/test_episode_f_join.py tests/unit/test_episode_f_join_guards.py`, 190 passed. Tests cover a retry that keeps a concurrent marker, stopping once the join no longer stands, and the bounded attempt count. Not verified in production; after deploy, check for the `pending_conflict` log line and F fallbacks per hour against the 1 to 4 seen on 2026-11-09.
