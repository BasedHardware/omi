# Recording-scoped custody wait no longer pauses the account drain

`record_capture_pending` (the retryable 503 a registered-record WAL gets while
exact coverage is unproven, record jobs are missing, or the owner context does
not match) no longer sends `Retry-After: 30`. Contract section: "named safety
WALs and recording-session WALs" in `../../listen_pusher_pipeline.mdx`. The
status, body code and local-audio retention there are unchanged.

Why: released apps treat any 5xx with Retry-After as an account-wide
`backendBusy` pause, and the local drain is oldest-first. One conversation that
stayed in this wait was retried first on every pass and stopped every other
recording on the phone from uploading. On 2026-11-07 a single conversation took
517 of ~678 sampled `/v2/sync-local-files` 503s for one user.

Released-client behavior after deploy: the WAL is handled as an unscoped 5xx.
It stays pending without spending its retry budget, is skipped for the rest of
that drain pass, and the drain continues with other recordings after the
client's own short pause (2–30s, reset by a success).

New app builds read the closed body code `record_capture_pending` on a 5xx and
never turn it into an account pause, whatever headers arrive. They mirror it as
a `deferred` upload, not a failure.

No flag, data migration or backfill. Rollback is reverting the change. This
does not resolve the wait itself; conversations stuck in `record_jobs_missing`
still need their record lane repaired (for example the no-job seal backfill).
