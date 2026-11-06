# Batch worker failure evidence chain

Failure-Class: FC-batch-transient-worker-failure-quarantines-blind-without-stage-or-reason-evidence

Every unit that fails its GPU work used to end one of two ways: a typed,
closed-code terminal handoff (`ValidationFailureWork` / `RecoveryWork`) that
quarantines immediately with a named stage and reason, or an ordinary
retryable failure (`FailedWork`) that dropped its diagnosis at the
worker → pump → scheduler boundary. The retry ladder then burned its five
attempts blind, and the terminal quarantine logged
`stage=unknown worker_reason=unclassified` — a signature that names neither
the stage nor the reason, so operators (and the log sensor) could not tell
which stage actually failed.

## What changed

- `FailedWork` carries an optional `worker_failure` evidence pair,
  `{'stage', 'reason'}`. Evidence is diagnostic only: it never decides a
  transition. An ordinary failure still rides the same bounded ladder and
  quarantines at the same attempt ceiling as before.
- The diarizer worker closes every ordinary failure into evidence at the
  source (`transient_failure_evidence`): closed stages produce a closed
  stage token; `BatchValidationError` reasons pass through; generic
  exceptions collapse to the enum's own `unknown` token. The untyped
  provider stages (`asr`, `persist`, `diarize`) stay unevidenced rather
  than inventing a token.
- `Scheduler.fail` accepts `worker_failure_evidence`, validates it with the
  dedicated evidence gate, and records the latest diagnosis on the job
  document inside the same transaction. Evidence survives later
  evidence-less attempts (a crashed worker does not erase the previous
  diagnosis), is replaced by a later evidenced attempt, is cleared on
  completion, and is retained on the quarantined job for operator recovery.
- The terminal quarantine log names the strongest diagnosis it holds:
  structured `worker_failure` first, then evidence, then the historical
  `unknown` / `unclassified` shape for a never-diagnosed unit.

## Log shapes

- `event=batch_quarantined reason=worker_failed attempt=5 recovery=held
  stage=fetch_decode worker_reason=unknown` — an evidenced ladder.
- `... stage=word_clocks worker_reason=word_clock` — a closed validation
  reason carried through the ladder.
- `... stage=unknown worker_reason=unclassified` — unchanged historical
  shape when no diagnosis ever reached the scheduler (worker crash, lost
  result, lease-expiry path).
- `event=batch_retry reason=worker_failed outcome=deferred attempt=N` —
  unchanged.

## Vocabulary

Evidence stages are the shared closed worker stage set (`fetch_decode`,
`vad_windows`, `word_clocks`, `assemble_words`, `asr_recovery`). Evidence
reasons are the full `WorkerValidationReason` enum including `unknown`;
the terminal gate (`validate_worker_failure`) stays strictly closed
(excluding `unknown`), because evidence never decides a transition while a
typed terminal handoff does. Exception messages never enter evidence or
logs.

## Operator response

A quarantined job whose document carries `worker_failure_evidence` names
the stage that burned the ladder. `stage=fetch_decode
worker_reason=unknown` points at staged-bytes decode; `word_clocks` with a
closed reason points at recognizer output clocks. Quarantined units keep
their encrypted audio and `recovery_state=held` custody exactly as before;
the fenced recovery path and runbooks are unchanged.
