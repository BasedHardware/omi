# Batch persist stage: closed evidence end to end

Every worker fault carries a closed `{stage, reason}` diagnosis into the
scheduler's ladder, so the terminal quarantine record names the boundary
that failed instead of an anonymous shape. The persist tail — payload
assembly, encrypt/upload and the durable artifact register that settles a
completed GPU unit — was the one worker boundary excluded from that
contract: it attributed its faults with `fail(item, exc, 'persist')`, but
`persist` was not a member of the shared `WorkerValidationStage`
vocabulary.

## What burned

- `transient_failure_evidence` refused the stage and returned `None`, so the
  `FailedWork` handoff crossed the pump evidence-less on every attempt.
- `scheduler.fail` stored no diagnosis on the job, and a persist-stage typed
  verdict raised `ValueError('closed worker validation failure required')`
  out of `validate_worker_failure`, crashing the publication transition it
  rode.
- A unit whose ladder exhausted on persist faults terminal-quarantined with
  the historical anonymous shape — `event=batch_quarantined
  reason=worker_failed ... stage=unknown worker_reason=unclassified` — the
  sensor's unattributed worker-fault bucket, even though the worker's own
  `event=batch_worker_failed ... stage=persist` ERROR line already named the
  boundary.

## The change

`WorkerValidationStage` gains `persist`. The evidence chain needs no other
code change: `transient_failure_evidence`, both store gates
(`validate_worker_failure`, `validate_worker_failure_evidence`), the
scheduler's ladder storage, the terminal-record naming and the
designed-handoff demotion predicates all key off the shared enum.

Generic persist faults close `{'stage': 'persist', 'reason': 'unknown'}`;
typed reasons pass through; off-vocabulary reasons collapse to `unknown`
(exception text never reaches the evidence). The ladder preserves the
diagnosis across evidence-less attempts, and the terminal record now names
`stage=persist worker_reason=<closed reason>` on the ERROR channel — persist
faults are real faults (a storage or register outage is not a designed
handoff), so none of the demotion families claims them: the empty ladder and
language-guard arms are reason-bound, the unconditional disposition arm is
fetch_decode-bound, and the flagged disposition arm only fires under the
same switch that decided the durable chain end.

Failure-Class: FC-persist-stage-failure-quarantines-anonymous-without-stage-evidence
