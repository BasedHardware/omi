# Retained projection hold expiry and nightly re-drive

Assignment-held receipts receive a seven-day `held_deadline_at`. The release
transaction backfills legacy holds and marks aged, still-unrestorable holds with
`held_expired_at` and `held_expired_reason=held_expired`, retaining the physical
`quarantine_held` state, result and receipt. At the release-attempt cap, the same
CAS retains the old count in `held_expired_release_attempts` and resets the active
counter so the unchanged pre-4b release implementation can still recover the row.

The default-on `BATCH_HELD_DEAD_LETTER_ENABLED` switch stops new stamps and
expiry. Frozen pre-change scan/release tests prove flag-off rollback recovery,
including the capped case, only when the target becomes restorable. The bounded
nightly helper also recovers marked rows with the switch off. Its durable cursor
continues across UTC midnight. Existing release cursors and privacy/custody fences
are unchanged. See the [runbook](../../runbooks/batch-held-dead-letter.md).

The agent-only volume alert keys on additive expiry markers and excludes
unrelated legacy holds. No deletion, conversation status, BYOK or finalization
change is included. Synthetic and loopback tests cover payload retention, CAS,
legacy recovery, entry stamps, backfill and bounded scans. Production stock,
live re-drive and alert delivery were not measured. See the
[pipeline contract](../../listen_pusher_pipeline.mdx).
