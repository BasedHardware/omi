# Held re-drive grants and spent transitions

PR: [#25012](https://github.com/BasedHardware/omi/pull/25012), pre-review fix
batch A–F under lead2 ruling 7a3c9e. The retained batch recovery contract is in
[the state-machine runbook](../../runbooks/backlog-state-machine.md); input
custody remains as described in [the pipeline contract](../../listen_pusher_pipeline.mdx#legacy-sync-staging-and-batch-cleanup-custody).

All held re-drive entry points share the existing content-owner/privacy fence
and held eligibility checks before granting a fresh attempt budget. The fence
is shared independently of recovery orchestration to preserve worker-image
source closure. Input-expiring operator requeues and staging-input repairs
consume no held grant and reset no attempt budget.

Client status polling refreshes its job snapshot from the transaction's staged
write after a successful re-drive. A newly ready unit returns queued with a
three-second poll hint; refused re-drives retain their held status and poll
hint. Regression tests cover both outcomes.

Durable held accounting continues when telemetry is silenced. The first
committed re-drive after three grants writes a durable spent marker and emits
one post-commit event when telemetry is enabled. Later cycles, refused rows,
expired-today skips and stale scan snapshots cannot emit another event. The
page observes new transitions over one hour; the retained loop has no new
terminal stop. Invalid counters log a content-free signal and normalize from
zero on the next verified re-drive; nonnegative integral floats are valid.

Defaults remain class 1 OFF, class 3 OFF and telemetry ON. All three switches
accept trimmed case-insensitive true; other explicit values fail closed.
Silencing telemetry changes no custody behavior. Sync GMP source filtering
now retains the spent-transition metric already imported by the exporter.

## Hermetic evidence — 2026-11-10T13:15:54Z

On m1-mac-studio, each file ran through backend/test.sh with xdist (two workers)
in its own pytest session: state machine 121, scheduler 62, held dead letter 42,
quarantine recovery 163, intake 85, input retention 108, monitoring telemetry
54, alert-rule contract 75, provisioning 27, alert backtest 28: **765 passed**.
Changed production modules passed pyright with the worktree interpreter:
**0 errors**. The feature-flag registry passed. Runtime source closure passed
for all 19 registered images. Full local preflight passed all 45 selected checks.
No live backend or production-data checks were performed.
