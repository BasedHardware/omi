# Batch language-guard redrive classification

## What changed in the classification

The GPU batch pipeline's language barrier — a unit whose frozen language the
batch Parakeet model cannot serve — ends the worker chain with the typed
closed code `unsupported_language`, quarantines the unit as held, and waits
for the fenced independent-recognizer recovery lane (Modulate, then Soniox)
to transcribe the retained audio. That transition is designed platform
behavior: typed refusal, affirmative speech evidence, no data loss, bounded
recovery below.

The refusal transition was logged through the worker-fault channels: the worker boundary emitted
`event=batch_worker_failed error_class=BatchValidationError ...` at ERROR and
the scheduler's terminal hold emitted
`event=batch_quarantined reason=worker_failed ...` at ERROR. Every guarded
unit therefore booked two production-error lines — the `stage=vad_windows
worker_reason=unsupported_language` family is a top sensor signature purely
because of that misclassification.

Both log sites now report the redrive transition at INFO:

- worker boundary transition record: `event=batch_language_guard outcome=redrive_held
  error_class=... stage=... segment_id=... reason=... samples=N vad_spans=N
  windows=N asr_words=N owned_words=N` (same fields the fault channel
  carried, including the `-1` "never measured" sentinels for units that fail
  before VAD).
- scheduler terminal hold transition record: `event=batch_language_guard outcome=held_for_redrive
  attempt=N recovery=held stage=... worker_reason=unsupported_language`.

The `event=batch_recovery outcome=held reason=awaiting_fenced_recovery`
WARNING still follows both lines.

## Where the barrier fires

The guard raises at any closed worker stage — `fetch_decode`,
`vad_windows`, `word_clocks`, `assemble_words`, `asr_recovery` — wherever the
frozen language meets the word provider it cannot serve; production burns it
at `vad_windows`.

## The demotion key

`utils.batch_pipeline.errors.LANGUAGE_GUARD_REDRIVE_REASONS` holds exactly one
closed reason: `unsupported_language`. The predicate
`language_guard_redrive_failure(failure)` demotes a terminal diagnosis only
when it is exactly the closed two-key `{'stage', 'reason'}` shape with a
closed stage and that reason. The predicate never raises on hostile input, and anything
anonymous — empty diagnoses, wider shapes, foreign reasons, off-vocabulary
stages — keeps its fault classification.

## What did not change

- Durable state: quarantined state, stored `worker_failure`, VAD bindings,
  padded-empty evidence handling, lease and admission accounting.
- The raise sites, the terminal chain end, and the fenced recovery lane:
  Modulate first, Soniox as the guarded second/independent provider, the 60 s
  independent ceiling, receipt shapes, words-repair eligibility.
- The `awaiting_fenced_recovery` WARNING, the `quarantined`/`recovery_held`
  queue metrics, `batch_retry` defers, and the `failed` correctness meter.
- The worker failure callback and every session close code.

## What stays on the fault channels

Every other closed reason keeps `event=batch_worker_failed` (worker) and
`event=batch_quarantined` (scheduler terminal hold) at ERROR, at every
closed stage: `staged_audio_invalid`, `retained_audio_invalid`,
`decoded_duration_mismatch`, `word_shape`, `word_clock`, `word_sequence`,
`vad_nonfinite`, `vad_order`, `vad_bounds`, `empty_asr`, `no_owned_words`,
`outside_admitted_source`, and the anonymous `unknown` shapes.

The unit's encrypted audio custody is retained the whole time — nothing is
deleted and nothing is re-encoded; the recovery lane re-reads the same bytes.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
