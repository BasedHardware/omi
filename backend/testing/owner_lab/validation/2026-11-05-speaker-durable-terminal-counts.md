# Durable speaker retry terminal counts — 2026-11-05

Synthetic local validation only. No production access, account data or GCP tier
was used. The parent owns the real-data gate and rollout decision. Flag defaults
were not changed. No amend, push or PR was performed.

Pre-rebase fix: `e2547944fd41df258137ee0c83ae746fa910fd6e`.
Final fetched/rebased main: `9ad243c066ac8a71efabc346c4467ec4d9c3917f`.
Rebased fix: `015d2ff6626ce4867d900a39051f6d9b8c70da5f`.
The initial fetch/rebase targeted `c37ad5003a10`; main advanced during checks,
so the branch was fetched/rebased again before final validation.

## Reporting policy

A process-local Prometheus increment cannot commit atomically with a Firestore
receipt. Keeping only the repair index would trade lost counts for duplicate
counts if emission succeeded and acknowledgement failed. The fix therefore
records retry outcomes in a durable sink: one transaction reads the reporting
receipt and its counter shard, increments the normalized outcome, and closes the
receipt. Its obligation key is the idempotency key. Both writes commit together;
an ambiguous reply, concurrent duplicate or process loss cannot duplicate or
lose the persisted count. Ineligible outcomes remain excluded. Reporting does
not consume another inference attempt or rerun enrichment/recurring learning.

There are 16 fixed counter shards containing only code-owned outcome counts.
Transaction reads use a three-second timeout without SDK read retries; the
transaction has one attempt, leaving transient recovery to the existing sweeper.
The maintenance sweep refreshes all shards in one bounded BatchGet even when no
receipt is due. An incomplete/failed snapshot never becomes a fresh observation,
and observation failure does not block pending-row repair. Scrapes do no IO.

`omi_transcription_final_pass_retry_terminal_total{outcome=...}` exports the
cached global counts; replicas mirror the same totals. Use `max by (outcome)`
before increases, then combine with initial-pass outcomes. Dedicated retries no
longer increment the initial-pass process counter. The refresh timestamp guards
against stale/missing data. GMP and the source-backed inventory include both new
samples alongside the existing counters and complete histogram families. The
historical observed inventory remains unchanged; old closed receipts are not
backfilled. Restart the rollout observation window after this metric change.
The [runbook](../../../docs/runbooks/batch-conversation-speakers.md#reading-final-pass-outcomes)
contains the combined query, freshness gate and outcome/reason table.

## Partial coverage and operator guidance

The runbook and owner-lab README now describe per-segment application: provable,
revalidated batch segments may update; unplaced, other-lane, point-only and
manual labels retain their authority. Partial coverage performs no recurring
learning. Shared, expired, merged or privacy-fenced inputs still refuse the
whole invocation. The runbook documents expiry, merge/shared-unit skips,
transient/custody deferrals, retry exhaustion, partial coverage and
`artifact_cleaned` as a reason rather than an outcome, plus the read-only
`final_pass_repro.py` path and its diagnostic fields. No tracked batch rollout
dashboard query outside this runbook required migration; the older sync cohort
failure guidance concerns its unchanged lane.

## Verification

All tests and checks used the worktree Python 3.11 environment through
`omi-heavy`.

- The commit-then-raise regression failed before the fix for ServiceUnavailable,
  DeadlineExceeded, Aborted and InternalServerError: zero reports instead of one.
- **1,029 focused tests passed before and after the final rebase**, across 24
  files. These include the maximum-size memory/deadline stress case and real
  multi-unit/mixed-authority `reproduce()` replay. The command is the previous
  [22-file focused command](2026-11-05-speaker-final-pass-transient-custody.md#rebase-and-verification)
  plus `test_batch_final_pass_outage.py` and `test_batch_final_pass_terminal_metrics.py`.
- **358 fast-lane tests passed before and after the final rebase**, one slow
  stress case deselected, through `test.sh` with one worker and the one-second
  CPU failure guard. Selected files: terminal metrics, outage, retry, transient,
  owner-lab, resources and lifecycle.
- New tests cover the SDK transaction callback with the strict read-order
  fixture, explicit committed-write/lost-reply faults, duplicate reporters,
  durable counter export after a replica restart, fixed-size bounded reads,
  incomplete/failed observations and continued custody repair. They prove no
  second inference or duplicate initial-pass metric. These are hermetic tests,
  not an emulator or live Firestore acceptance claim.
- Black formatted eight changed Python files; the commit hook confirmed all
  eight unchanged. `git diff --check` passed.
- **All 42 `make preflight` checks passed before and after the final rebase**,
  using local draft metadata, including monitoring lint, image source/dependency
  closure, import purity, async blockers, test isolation and authority fences.

Four GMP conflicts were resolved by unioning both sides' alternatives. A separate
check proved every alternative from fetched main and the pre-rebase branch was
retained, all 13 final-pass series matched, and all other YAML followed main.
The range-diff's only changed hunks are GMP keep-list context; the new reporting
code is unchanged by rebase. The outbox dependency stays out of the GPU
batch-pipeline worker closure; Pusher's finalizer reaches it through
`process_conversation` as before.
