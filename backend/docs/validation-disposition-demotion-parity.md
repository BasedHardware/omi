# Batch worker validation: the terminal disposition reports on its own channel

Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault

A terminal worker-validation disposition is the bounded GPU chain's
designed custody handoff for input no retry can repair — the sibling of
the language barrier and the empty ladder. Two arms decide it at the
worker boundary. The typed fetch_decode trio (`staged_audio_invalid`,
`retained_audio_invalid`, `decoded_duration_mismatch`) fails identically
on the pinned bytes on every attempt and ends the chain unconditionally.
Under the worker-validation disposition switch
(`BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED`, default on),
every closed vad/word validation verdict (`vad_nonfinite`, `vad_order`,
`vad_bounds`, `word_shape`, `word_clock`, `word_sequence`) ends it the
same way. Each hands the unit to the fenced independent-recognizer
recovery lane with its measured VAD evidence and receipt intact.
Nothing about the unit is faulted and no GPU retry can change the
verdict, so booking each disposition on the ERROR fault channels
misbooks a designed platform outcome as a production error. In
production this surfaced as the loop sensor's
`event=batch_worker_failed error_class=BatchValidationError
stage=vad_windows` and `stage=word_clocks` lines plus the scheduler's
`event=batch_quarantined reason=worker_failed ... recovery=held
stage=word_clocks worker_reason=word_sequence` line for the same
settled unit: two ERROR lines per settled unit, hundreds per 30
minutes, all of them the disposition working as designed.

## What changed

- A closed reason family and predicate,
  `validation_disposition_failure(failure, disposition_enabled=...)`,
  backed by `VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS` (the
  fetch_decode trio, stage-gated to `fetch_decode` where the typed
  classes raise nowhere else) and
  `VALIDATION_DISPOSITION_FLAGGED_REASONS` (the vad/word verdicts,
  answered at any closed worker stage — `fetch_decode`, `vad_windows`,
  `word_clocks`, `assemble_words`, `asr_recovery` — mirroring the
  boundary's stage-agnostic flag-gated arm)
  (`utils/batch_pipeline/errors.py`).
- The worker boundary reports the handoff as
  `event=batch_validation_disposition outcome=recovery_handoff
  error_class=... stage=... segment_id=... reason=... samples=...
  vad_spans=... windows=... asr_words=... owned_words=...` at INFO.
  Every diagnostic field the fault line carried is kept; only the
  event name, outcome token and severity moved. Shadow units keep the
  shadow line ahead of the classification.
- The scheduler's terminal quarantine reports the hold as
  `event=batch_validation_disposition outcome=held_for_disposition
  attempt=... recovery=held stage=... worker_reason=...` at INFO. Same
  durable state, same evidence booking, same `recovery_held` metric,
  same `event=batch_recovery outcome=held
  reason=awaiting_fenced_recovery` warning after every branch — only
  the ERROR line moved.
- Both sites consult the same family, the same stage tokens and the
  same `worker_validation_disposition_enabled` switch, so the
  disposition demotes together and nothing else does. The flagged
  verdicts demote only while the switch that decided the durable
  disposition is on: a ladder still walking its retries (switch off)
  keeps every fault line. The unconditional trio's demotion is
  unconditional, because its chain end is unconditional on pinned
  bytes.
- The scheduler accepts the predicate in the same closed shape the
  language guard and empty ladder accept: exactly the two-key
  `{'stage', 'reason'}` dicts the store validators admit. Anonymous,
  foreign, off-vocabulary or hostile input keeps the fault
  classification; the predicate never raises on hostile input.

## What deliberately did not change

- `outside_admitted_source` keeps its ERROR lines: the bytes may be
  sound and a later deploy can admit the source, so the bounded retry
  ladder keeps walking by design — a fault-classification line for a
  fault-classified path.
- Every unclassified or unknown fault keeps its ERROR lines, at every
  stage. The demotion is closed-vocabulary only.
- Durable state, evidence booking, correctness meters, custody and the
  awaiting-fenced-recovery warning are unchanged. The demotion
  rechannels the report only.
- The durable disposition decision itself (`fail()` at the worker
  boundary, `ValidationFailureWork` vs `FailedWork`) is unchanged; the
  change is the two reporting sites.

## Rollback

Set `BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED=false` to
restore the bounded GPU retry ladder for the flagged verdicts — the
demotion follows the same switch, so the fault lines return with the
ladder. The unconditional trio's chain end and demotion are tied to the
pinned bytes, not to a switch; reverting the commit restores its ERROR
lines.
