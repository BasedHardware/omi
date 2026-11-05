# Batch pipeline: a word past the window's captured extent is unowned, not a clock defect

The GPU worker owns ASR words by midpoint (`bounded_window_words` in
`diarizer/batch_pipeline.py`): a word whose clock midpoint falls inside the
window's captured extent is kept and has its edge-straddling clocks clamped to
the capture; a word whose midpoint falls outside is dropped. The same function
also raised `WORD_CLOCK` when a word's *start* clock sat at or after the
window's end — before the midpoint rule could ever classify it. That raise
turned a benign recognizer tail artifact into a unit-killing validation
failure: the whole already-paid hypothesis was discarded, the unit quarantined
on its first attempt (`attempt=1 recovery=held`), and the fenced recovery lane
was asked to re-recognize audio it could not use to recover a word the window
never contained.

Prod evidence (worker `batch_quarantined attempt=1 recovery=held
stage=word_clocks worker_reason=word_clock`, 32/30m on 2026-11-04, plus the
matching `diarizer.batch_pipeline event=batch_worker_failed
error_class=BatchValidationError stage=word_clocks` line): every burn of that
signature is a hypothesis in which at least one word began at or after its own
window's end — the replay corpus's `word-clock-eof` incident shape is exactly
this (a 0.5 s window whose mutated hypothesis starts a word at 0.6 s). A word
that begins at or after the extent of the audio it was decoded from cannot be
owned by that window under the pipeline's own midpoint contract; failing the
unit for it converted a drop into a quarantine plus a second paid recognition
of the same audio.

## What changed

- One boundary: `bounded_window_words` now drops the out-of-extent tail word
  (`start >= duration`) instead of raising, and leaves every other clock rule
  exactly where it was. The drop happens before the monotonic-sequence check
  and does not advance the sequence pointer, so kept words on both sides of a
  dropped tail keep their original order and clocks.
- Nothing else moves. Malformed clocks — nonfinite start or end, reversed
  clocks, negative end, and the `end == 0 and start < 0` shape — still raise
  `WORD_CLOCK`; unparseable timestamps still raise `WORD_SHAPE`; reversed or
  blank kept words still raise `WORD_SEQUENCE`. Kept-word ownership, midpoint
  clamping, left-context handling and the unit-level `validate_words` strict
  bound (+10 ms) are byte-identical. The padded-retry adapter
  (`diarizer/batch_pipeline_models.py recover_empty`) already pre-filtered its
  hypotheses with the same midpoint rule, so its behavior is unchanged.
- The only behavioral regression surface is the empty window: a hypothesis
  whose every word began past the window end now owns nothing and follows the
  ordinary empty-ASR path — the same `empty_asr` envelope, quarantine shape
  (`attempt=1 recovery=held`), padded/context retry and fenced recovery lane
  every other benign recognizer-empty outcome rides. That lane is the
  well-served one (strict-silence disposition, terminal-empty evidence,
  redrive census); the `word_clocks` envelope had no dedicated disposition.

## Contracts that do not change

- The reason code surface: `word_clock` remains a closed `ValidationReason`
  emitted only for genuinely malformed clocks; the failure envelope
  (`ValidationFailureWork(stage, reason)`) is untouched.
- Word ownership across context seams: prefix words are never owned by the
  unit, straddling words clamp to the capture, and the midpoint rule keeps
  deciding ownership exactly as before — the drop only removes the raise that
  pre-empted it for words the rule would have discarded anyway.
- No durable state is introduced: quarantined units, receipts and evidence
  fields are byte-identical for every unit that still fails, and units the
  raise used to kill now publish their kept words through the ordinary
  persist path.

## Rollback

Revert the one boundary in `bounded_window_words` (restore `start >= duration`
to the malformed-clock raise). No state migration is involved; the replay
corpus and the parity suite pin both the old failure shapes for malformed
clocks and the new drop, so either side of the boundary is observable.

Failure-Class: FC-model-time-outside-captured-samples
