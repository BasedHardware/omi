# Backlog state machine (batch and sync)

Code: `config/backlog_state_machine.py`, `utils/backlog_metrics.py`.
Tests: `tests/unit/test_backlog_state_machine.py`.
Alerts: `charts/monitoring/alerts/backlog-state-machine.json`.

Backlogs recurred because several state machines handed work to each other and
no state owned its exit: a retry cap that only observed, a counter that reset on
lease expiry, re-drives that kept the attempt count at the cap, and rows with no
deadline at all. The rule now: **every non-terminal state has one owner, one
deadline and one counter, and every automatic loop has a terminal stop.**
Terminal stops retain content. None of them deletes audio, results, custody
tokens or privacy fences, and each has an operator exit.

## State table

| State | Owner (who moves it) | Deadline / counter | Exit | Terminal stop |
| --- | --- | --- | --- | --- |
| batch `leased` | scheduler `recover` | lease; `attempt` vs `BATCH_PIPELINE_MAX_ATTEMPTS` (5) | `retry`, or `quarantined` at the cap | quarantine (retained) |
| batch `quarantined` (held) | held dead-letter sweep | `held_deadline_at` (7 d) | `dead/held_expired` | (next row) |
| batch `dead/held_expired` | nightly re-drive | `held_redrives` vs `MAX_HELD_REDRIVES` (3) | `ready` with `attempt=0` | `dead/held_exhausted` (retained, operator requeue) |
| projection `quarantine_held` | release scan + nightly re-drive | `projection_release_attempts` (3); `held_expired_rearms` (3) | `pending` when target restorable | re-arm stops; receipt retained as `held_expired` |
| projection assignment hold (`persisted`, job `recovery_state=held`) | release scan, assignment leg | **none** (see open question) | `pending` when target restorable | operator redrive only |
| sync owner `dispatching` | sequencer sweep | `dispatch_retry_at`; `dispatch_attempt` vs `SYNC_TASKS_MAX_ATTEMPTS` (cap enforced only in the `CAPTURE_COVERAGE_MODE` cohort: a passed retry deadline is queue delay, not failure) | redrive or finalize | job failed `sync_dispatch_exhausted` (cohort only) |
| sync owner `running` | sequencer sweep | `lease_expires_at`; `running_expiries` vs `SYNC_TASKS_MAX_ATTEMPTS`; `dispatch_attempt` carried | redrive (`epoch+1`) or finalize | job failed `sync_dispatch_exhausted` |
| `record_pending` (young) | record drain | barrier backoff ladder (#24863) | admission | (next rows) |
| `record_pending`, conversation missing | `record_pending_repair` | 7 d | `cancelled` | cancelled (audio retained) |
| `record_pending`, conversation completed, barrier open | seal repair | seal repair proofs | admission after seal | seal repair refusal (unchanged) |
| `record_pending`, conversation present and not completed | record drain | 14 d, then weekly; `barrier_redrives` vs 4 | admission if it completes | `barrier_dead_letter` park (retained, operator requeue) |

## Switches (safety kill switches, on unless set to anything but `true`)

All four are in `config/policy/kill_switches.py` and `config/feature-flags.yaml`.
Set one to `false` to restore the exact previous transition. They are read per
decision, so a change takes effect on the next sweep, drain or requeue without a
restart. No row needs a migration either way. Fields written while a switch was on
(`held_redrives`, `barrier_redrives`, `held_expired_rearms`) are inert when it is
off.

| Switch | Bug class | Turning it off |
| --- | --- | --- |
| `CAPTURE_RETRY_CAP_ENFORCED` | 1: the cap observed but never ended work | Batch lease-expiry and sync running caps return to the `CAPTURE_COVERAGE_MODE` cohort (shadow outside it) |
| `SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED` | 2: running lease expiry reset `dispatch_attempt` to 0 | Running expiry resets to 0, `running_expiries` stays 0, and only dispatching owners are capped |
| `BATCH_HELD_REDRIVE_BUDGET_ENABLED` | 3 and 6: requeue kept `attempt` at the cap; no terminal stop | Requeue keeps `attempt`; nightly re-drive and projection re-arm are unbounded again |
| `RECORD_PENDING_BARRIER_DEAD_LETTER_ENABLED` | 4: unfinished conversations retried forever | Aged rows stay on the hourly barrier ladder |

### The flip of the retry cap (class 1)

Before this change the cap's enforcement rode on `CAPTURE_COVERAGE_MODE`, whose
serve ramp is gated on unrelated dedupe evidence. With the default `shadow` mode
the cap only logged `would_quarantine`. Now:

- Batch: a unit whose lease expires at `BATCH_PIPELINE_MAX_ATTEMPTS` is quarantined
  (`quarantine_reason=worker_failed`, `recovery_state=held`), the same transition an
  explicit worker failure already took. It then follows the held rows above.
- Sync: a running owner whose `running_expiries + 1` reaches
  `SYNC_TASKS_MAX_ATTEMPTS` (the job began and its lease expired with no run lock,
  that many times) is finalized by the existing fenced finalizer
  (`sync_dispatch_exhausted`), which refuses while a run lock or a renewed lease
  exists. Budget-deferral chains keep their own `budget_chain_exhausted` terminal.
- Not changed: the dispatching-state cap (`dispatch_attempt`) stays on the
  `CAPTURE_COVERAGE_MODE` cohort. A passed dispatch retry deadline only means the
  queue has not delivered yet; a backlogged queue delivers hours late, so
  enforcing that count by default would fail runnable jobs
  (`FC-queued-delivery-invalidated-by-redrive`;
  `test_delayed_queue_dispatch_retries_are_not_terminalized_by_default`).

Watch `omi_capture_retry_cap_total{outcome="quarantine"}` (alert
`omi-backlog-retry-cap-quarantine-rate`). A spike after deploy means units that
used to loop are now being held. That is the intended effect, but check
`check=scheduler_lease_expiry` worker failure reasons before deciding it is not a
regression. Rollback: `CAPTURE_RETRY_CAP_ENFORCED=false`.

## Operator exits

- Held batch unit, including `dead/held_exhausted`: the private OIDC
  `POST /v2/batch-pipeline/requeue-quarantined` (`RecoveryStore.requeue_quarantined`
  without `dead_before`). It grants one fresh attempt budget and counts it.
- Parked `record_pending`: `utils.batch_pipeline.live.requeue_barrier_dead_letter(store, segment, now)`
  makes the row due now with a fresh re-drive budget and keeps the parked record
  in `barrier_dead_letter_history`.
- Assignment holds: the reviewed operator redrive intents in
  `database/batch_pipeline_projection.py` (unchanged).

## Open question for David

C7 is settled by `test_assignment_held_releases_automatically_only_when_target_restorable`:
a restorable assignment hold releases automatically (release scan, assignment
leg, on by default with `BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED`). An
unrestorable one never gets a deadline, because `persisted` rows still owe
multipart follow-ups and are excluded from expiry. That cohort remains the one
state without a deadline. Giving it one would let expiry mark a receipt that
still owes follow-ups, so it needs a ruling, not a default.

## Metrics

`omi_backlog_state_transitions_total{transition}`: `held_exhausted`,
`projection_rearm_exhausted`, `record_barrier_redrive`,
`record_barrier_dead_letter`, `sync_running_cap_reached`. Counted once per
committed transaction, never inside a retryable callback.

`omi_batch_held_expired_units` (the retained dead-letter stock) still counts
only `dead_letter_reason=held_expired` jobs. A unit that moves to
`held_exhausted` leaves that stock and is counted by the `held_exhausted`
transition instead, so add both when sizing retained held work.

The lifecycle `record_pending` oldest-age gauge still counts parked rows: they
remain `state=record_pending` on purpose (merge order, seal repair, the
missing-conversation cancel and erasure all key on it). Read the parked count
from `record_barrier_dead_letter` before treating oldest age as live debt.
