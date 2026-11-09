# Token lease round-2 review corrections

This applies the lead's five decisions from the two FIX-FIRST re-reviews of
`b70acd27e098`. It supersedes the rollback/recovery descriptions in the
[earlier receipt](2026-11-09-token-lease-review-fixes.md) and updates the
[custody contract](../../listen_pusher_pipeline.mdx).

The branch was rebased onto freshly fetched `origin/main`,
`82969e2b845b4f1c76d78f63272ad83b11cf9aa0`. No Part B changes are introduced.

Recovery reads the original job's captured input revision, without a
conversation-status gate. A newer revision creates or rearms the existing
partial continuation, retaining original units and waiting for any older full
publication. Legacy captured jobs without the new revision field are handled
conservatively. An uncaptured reservation stays on normal admission, which
reads the current upload barrier and validates it transactionally after staging.
Lease-enabled native admission pins `record_input_upload_revision`; off-mode
admission retains its previous payload. Recovery remains explicitly partial.

A custody fence acquired in serve is a durable obligation: accepted stored
bytes still revise and recover after rollback. Podless custody fences retain
their own lease exit in every mode, including after a crash; off-mode frame
pod/abandon proof remains unchanged. The clock parser now accepts the explicit
clocks on these podless custody tokens.

Frame fence/renewal transactions report a late observation without incrementing
the late-append counter. Only a successful durable-window/object commit consumes
that observation. Refused/failed storage does not count, and an older in-flight
window cannot consume a later observation. Custody counting still follows
accepted durable storage.

Private-cloud-sync-disabled uploads skip custody fences. If archiving becomes
disabled after fencing and returns no paths, finalization clears only that
fence without bumping revision or creating recovery; the original route response
is preserved. If cleanup is unavailable, the existing token's lease remains the
exit and the original response is still preserved.

The active production repair CronJob now serves its existing shared probe
collectors plus the bounded oldest-unsealed discovery sample on port 9090.
Its PodMonitoring scrapes `/metrics` every 15 seconds. The idle seal worker's
runtime setting is unchanged. The backlog expression filters idle NaN samples,
aggregates the actual repair age, and carries the last valid sample for ten
minutes across short CronJob gaps before deriving its slope. Pod replacement
cannot invent a flat per-pod trend or reset the warning's hold period.
Only this branch's backlog alert expression and its mirrors are updated; main's
existing alert entries are preserved.

Mode defaults remain off; the 3600-second default, 48-hour shadow soak and
lead/P4 ramp gates remain unchanged. No production access, push or PR is part
of this work. GCP tier: none.

## Validation

Initial focused validation passed token lease (80), custody append (26), partial
recovery (82), deployment/HTTP telemetry (9), native admission (102), and producer
proof (27). The new pusher fixture initially omitted its explicit runtime stage;
the fixture was corrected without relaxing an assertion. Final focused,
all-backend conformance, lifecycle, alert/telemetry and expanded preflight results
are recorded below after the complete run.

The real-engine backtest runner is `tests/promql/record_token_lease.py` (run from
backend with `--promtool <path>`). It reads the checked-in Grafana expression
and its threshold/hold period, then tests rotating repair pods with idle NaN,
healthy falling age, no recent releases, and no valid repair sample.
