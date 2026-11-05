# Batch pipeline: sub-second speech rides the same context-bearing empty retry

The GPU worker's empty-ASR retry picks its audio by measured VAD speech. The
eligibility boundary was `speech_seconds >= 1`, so a unit carrying a positive
but sub-second measure of VAD speech fell back to retrying its byte-identical
raw samples. That is a scheduled failure under the documented Parakeet TDT
start-state mechanism (`diarizer/batch_pipeline_context.py`: a clip that
starts mid-utterance decodes nothing — blank beats every token from the
decoder start state — and capture units are cut at fixed upload boundaries),
and the predecessor-tail prefix plus onset trim exist precisely to break it.
The strict-VAD contract already rejects the shortcut of treating those units
as disposable: "a recognizer returning blanks cannot establish that
VAD-positive audio is disposable, including sub-second speech"
(`config/batch_pipeline_empty_asr.py`).

Prod evidence (worker `batch_quarantined attempt=1 recovery=held
stage=assemble_words worker_reason=empty_asr`, the loop sensor's top
signature at 388/30m on 2026-11-04): quarantined empty-ASR units carry
measured speech, mostly under two seconds (13 of 13 since the 2026-11-02
epoch, 10 under 2s — `charts/monitoring/batch-projection/README.md`). With
`BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED` dark in prod, a quarantined
sub-second unit has no automatic second chance: its transcript never
publishes and it stays in the 2-hour timeliness alarm (the 2026-11-01
lost-segments class).

## What changed

- One boundary: the retry's audio selection is now measured-speech-gated at
  `> 0` instead of `>= 1` (`diarizer/batch_pipeline.py`). Every
  measured-positive band rides the same single context-bearing retry:
  predecessor tail prefix when the flight/tail cache knows a contiguous
  same-owner predecessor, otherwise the onset trim.
- Nothing else moves. The retry still runs exactly once per unit, still
  through `padded_retry_fits` (the `room` arithmetic already guarantees a
  prefixed retry fits the 120s bound), still through the capacity
  re-dispatch hold, still subject to the `near_empty_words` debris filter —
  which stays measured-speech-gated at `>= 1`, so a sub-second "OK"/"I"
  hypothesis publishes as before. Measured-zero units keep the raw retry:
  the strict silence contract, not recognition, is their terminal authority.
- Downstream state is unchanged: the same `padded_retry`
  (`recovered`/`empty`/`skipped_oversize`/`skipped_long_speech`) tokens, the
  same `RecoveryWork` shape, the same quarantine-on-empty custody
  (`attempt=1 recovery=held`), the same worker VAD receipts. A sub-second
  unit whose context retry still comes back empty lands in exactly the prod
  signature shape as before — only the units the prefix actually rescues
  publish instead of quarantining.

## Contracts that do not change

- The kill switch: `BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED=false`
  restores the raw-sample retry for every band (and empties the tail cache),
  exactly as before.
- The fenced recovery and silence-disposition gates
  (`BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED`,
  `BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED`) stay dark by default; this
  change is worker-side only and adds no provider spend beyond the one
  context-bearing retry the failure path already paid for sub-second units.
- Word ownership: prefix words are never owned by the unit (midpoint
  ownership and `retry_offset` mapping are untouched), so nothing is
  double-counted across the seam.
- The first-pass left-context attach stays config-gated
  (`BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS`); it already applied to
  sub-second units regardless of this change.

## Rollback

Revert the one eligibility boundary (restore `>= 1`). No durable state is
introduced by this change: quarantined units, receipts, and evidence fields
are byte-identical to the previous behavior.

Failure-Class: FC-subsecond-vad-speech-empty-retry-resends-identical-audio
