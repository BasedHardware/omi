# Fetch-decode gone-artifact custody (`decode_artifact_missing`)

Every batch unit's fetch_decode reads its staged or retained audio through a
generation-pinned storage reference: the manifest names a bucket, a path and a
generation, and `read_reference` pins the same generation on both its GET
(`blob.reload`) and its DOWNLOAD (`download_as_bytes`) with no internal retry.
When the object is gone — the retention sweep, the staging GC, the raw-audio
discard sweep or an expired staging window removed it — both calls answer the
same 404 (`NotFound`) on every attempt: a deleted object never comes back at
the pinned generation, so identical input reproduces the fault exactly.

Before this change the worker boundary had no arm for that loss. Each ladder
attempt re-ran the full GPU pipeline on bytes that could not change, booked one
anonymous `batch_worker_failed error_class=NotFound stage=fetch_decode
reason=unclassified` ERROR line, and after five attempts the unit quarantined
blind on the anonymous `stage=unknown worker_reason=unclassified` channel. The
sensor's NotFound cohort at fetch_decode is that loop.

## The fix

The boundary now types the loss and ends the chain at its first occurrence:

- `diarizer.batch_pipeline.decode_artifact_loss_is_deterministic` answers True
  for `NotFound` and nothing else. The verdict reads the exception type only —
  never a message — mirroring the decode-poison and persist-refusal verdicts,
  so it cannot drift with storage wording.
- `fail()` consults it only at the `fetch_decode` stage and only for a fault
  still carrying the anonymous `unclassified` attribution (`decode_artifact_failure_reason`),
  so the typed decode trio, the poison, the persist tail's verdicts and every
  transport family keep their existing custody. A `NotFound` raised by a later
  stage's upload is that stage's fault, not a fetch read loss.
- The chain ends via the same terminal route the decode trio rides
  (`ValidationFailureWork`): custody is retained for the fenced
  independent-recognizer recovery lane with the measured VAD evidence and
  receipt intact. No GPU retry is spent on a read that cannot change.
- The token `decode_artifact_missing` joins the closed worker-validation
  vocabulary (store validators, durable evidence) and the unconditional
  disposition family in `utils.batch_pipeline.errors`, so both terminal
  reports (the scheduler's verdict terminal and the recover sweep's
  lease-expiry cap terminal) demote the designed handoff off the ERROR
  quarantine channel to its INFO transition line. The demotion rechannels the
  report only: durable state, evidence, metrics, custody and the
  awaiting-fenced-recovery warning are unchanged.

## The recovery lane completes the custody

The custody handoff names a consumer: the worker ends the chain and retains
the unit "for the fenced recovery lane", and the held unit's manifest stays in
place for that lane to settle. But the sweep's own fetch — the
generation-pinned read it performs on every recovery attempt — had no arm for
the gone-object verdict either. A `NotFound` from `fetch_audio` escaped all
four typed decode-invalid arms, propagated out of the recovery intent, and was
booked by the sweep's per-unit fault handler as an anonymous
`event=batch_quarantine_recovery action=dispatch outcome=retry
exception_type=NotFound` line with the unit kept `prepared`. Because
`failed_held` units leave the recovery candidate set but retrying ones never
do, that booked the same unit on every sweep forever: one paid
generation-pinned GET plus one anonymous ERROR line per held unit per pass —
the loop the sensor sees as a persistent fetch_decode NotFound cohort even
after the worker boundary was fixed.

The sweep's fetch now carries the missing arm. The closed family lives in one
place (`utils.batch_pipeline.quarantine_recovery.RECOVERY_FETCH_REFUSALS`):
the four typed decode-invalid classes keep their tokens, and the storage 404
joins with the worker boundary's own `decode_artifact_missing` token, so the
unit's evidence names the same family end to end. The settle rides the same
`hold_invalid_manifest` CAS the typed arms ride: the unit reaches
`failed_held` once, leaves the candidate set, and neither a Cloud Tasks retry
nor a later sweep re-reads it. Everything the family does not claim — the
transport and contention families (429/5xx/`Aborted`), a bare `ValueError` at
this surface (retryable by its pinned fixture), privacy and projection fences
— re-raises and keeps its existing verdict and retry budget. The arm reads no
switch: the settle is decided by the pinned bytes' fault class alone.

## Expected production shape after the sweep arm ships

- The anonymous `action=dispatch outcome=retry exception_type=NotFound` lines
  disappear; each affected held unit books exactly one
  `event=batch_quarantine_recovery outcome=failed_held
  reason=decode_artifact_missing` INFO transition and is never fetched again.
- One paid generation-pinned GET per gone unit per sweep becomes one GET per
  gone unit total.
- The typed decode-invalid siblings keep their existing event names and
  tokens; transient storage storms keep walking the retry budgets they are
  shaped for.

Failure-Class: FC-decode-artifact-notfound-custody-reattacks-the-gone-object-every-recovery-sweep

## Expected production shape after ship

- `error_class=NotFound stage=fetch_decode reason=unclassified` disappears:
  each affected unit books exactly one
  `event=batch_validation_disposition outcome=held_for_disposition`
  INFO line at its terminal instead of five per-attempt ERROR lines plus an
  anonymous terminal quarantine.
- GPU ladder spend drops by up to four full pipeline re-runs per affected unit.
- The transport families (`Aborted` / `ServiceUnavailable` /
  `DeadlineExceeded`) and the shared contention classifier's verdicts are
  untouched and stay deliberately retryable; a transient storage storm keeps
  walking the ladder it is shaped for.

Failure-Class: FC-fetch-decode-artifact-notfound-walks-gpu-ladder-as-unclassified-worker-fault
