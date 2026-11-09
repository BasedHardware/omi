# Batch empty ladder: the recovery handoff reports on its own channel

Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault

A terminal empty verdict at `assemble_words` is the designed recovery
handoff, the sibling of the language barrier: a typed
`BatchValidationError` (`empty_asr` / `no_owned_words`) that the bounded
context-bearing retry already ran, a `RecoveryWork` handoff carrying the
retry and VAD evidence to the scheduler, and the fenced
quarantine-recovery lane waiting below the terminal hold. Nothing about
the unit is faulted and no worker retry can change the verdict, so
booking each held unit on the ERROR fault channels misbooks a designed
platform outcome as a production error. In production this surfaced as
the loop sensor's `event=batch_quarantined reason=worker_failed
attempt=1 recovery=held stage=assemble_words
worker_reason=empty_asr` signature (the scheduler terminal line) plus
`event=batch_worker_failed error_class=BatchValidationError
stage=assemble_words` (the worker boundary line for the same unit):
two ERROR lines per empty unit, hundreds per 30 minutes, all of them
the ladder working as designed.

## What changed

- A closed reason family, `EMPTY_LADDER_RECOVERY_REASONS =
  {'empty_asr', 'no_owned_words'}`, and the stage the ladder owns,
  `EMPTY_LADDER_RECOVERY_STAGE = 'assemble_words'`
  (`utils/batch_pipeline/errors.py`). The family members are exactly the
  reasons `empty_ladder_handoff` rides to the `RecoveryWork` handoff with
  the safety net on; they raise nowhere but `assemble_words`.
- The worker boundary reports the handoff as
  `event=batch_empty_ladder outcome=recovery_handoff error_class=... stage=...
  segment_id=... reason=... samples=... vad_spans=... windows=...
  asr_words=... owned_words=...` at INFO. Every diagnostic field the fault
  line carried is kept; only the event name, outcome token and severity
  moved. Shadow units keep the shadow line ahead of the classification.
- The scheduler's terminal quarantine reports the hold as
  `event=batch_empty_ladder outcome=held_for_recovery attempt=...
  recovery=held stage=... worker_reason=...` at INFO. Same durable state,
  same evidence booking, same `recovery_held` metric, same
  `event=batch_recovery outcome=held reason=awaiting_fenced_recovery`
  warning after both branches — only the ERROR line moved.
- Both sites consult the same family and the same stage token, so the
  ladder demotes together and nothing else does. An empty-family token at
  any other stage (a synthetic `empty_asr` raised at `fetch_decode`, for
  example) keeps its fault classification: the stage gate is part of the
  predicate, not a side effect of the raise sites.
- The scheduler accepts the predicate in the same closed shape the
  language guard accepts (`empty_ladder_recovery_failure`): exactly the
  two-key `{'stage', 'reason'}` dicts the store validators admit.
  Anonymous, foreign, off-vocabulary or hostile input keeps the fault
  channel and never raises.

## Unchanged accounting

- Quarantine custody: the terminal record still stores
  `quarantine_reason='worker_failed'`, the structured `worker_failure`,
  and the `worker_empty_evidence v1` booking when a padded-retry token
  rode the fail. Recovery candidates, the wake lease and the fenced
  settlement protocol are untouched.
- Metrics: `quarantined` and `recovery_held` still record for every
  terminal hold, demoted or not; the `empty_asr_attempt` correctness
  meter is untouched.
- The awaiting-fenced-recovery warning still follows both demotion
  branches, so held-volume alerting does not depend on the ERROR line.
- The empty ladder's retry eligibility (`empty_ladder_handoff`, the
  safety net, the recovery/disposition gates) is untouched: this change
  rechannels a report; it routes no unit differently.

## Why a reason family and not evidence gating

The closed reason vocabulary already decides fault versus outcome:
`word_shape`, `vad_bounds` and their siblings are worker faults; an
empty recognition verdict is not. The ladder's own evidence booking is
unchanged and stays on the job, so an undiagnosed empty (a missing
worker result on the exhausting attempt) still preserves the diagnosis
recorded by earlier attempts — the terminal record names the strongest
diagnosis it holds exactly as before.

## Verification

`backend/tests/unit/test_empty_ladder_channel_*.py` pin the predicate
contract, the worker and scheduler taxonomies, the worker↔scheduler
channel pair parity over the closed vocabulary, the doc parity, the
rollback matrix over the handoff flags, the unchanged durable-state and
metric invariants, the vocabulary membership, the pump routing that
feeds the channels, the sensor-line fates, and the live worker grid.
`test_language_guard_worker_boundary_log.py`,
`test_language_guard_scheduler_redrive_log.py`,
`test_empty_ladder_scheduler_evidence.py`,
`test_batch_pipeline_worker.py` and
`test_batch_pipeline_subsecond_empty_context_retry.py` were updated where
they pinned the empty family to the fault channels at `assemble_words`
— including the sub-second retry suite's own prod-signature pin, which
now asserts the `held_for_recovery` line; their cross-stage fault pins
still pass unchanged.

## Rollback

Revert the three hunks (the errors predicate, the worker boundary
branch, the scheduler terminal branch). Durable state is byte-identical
in both shapes, so rollback changes only the log channel: the fault
lines return immediately and no recovery, custody or metric surface
notices.
