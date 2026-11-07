# Owned recognition clocks: wholly-outside ghosts drop instead of failing the capture

`event=batch_quarantined reason=worker_failed attempt=1 recovery=held
stage=word_clocks worker_reason=word_clock` burns because a recognition clock
that lies wholly outside its captured extent failed the unit as a clock
defect. TDT start-state ghosts are the documented decoder behavior the padded
retry already exists for: a window cut from mid-utterance audio can carry the
predecessor's tail anchored at negative window-local time, and vendor or
model frames can quantize past the capture's end. The midpoint ownership rule
in `bounded_window_words` always declared such a word unowned — but the
pre-filter raised `WORD_CLOCK` on the pre-window side, discarding every kept
word of an already-paid hypothesis and quarantining the capture for a fenced
second recognition that cannot recover a word the capture never contained.
The CPU provider and recovery lanes validated with the strict tolerance
alone, so the same geometry quarantined there as an invalid response.

Failure-Class: FC-wholly-outside-recognition-clock-ghost-fails-the-capture-and-quarantines-kept-words-instead-of-dropping-unowned

## What changed

- `bounded_window_words` moved to `utils/batch_pipeline/word_validation.py`
  (its docstring already claimed GPU/CPU sharing) and now disposes clocks
  symmetrically: wholly before the window (`end < 0`, or zero end with a
  negative start) drops exactly like wholly at-or-past the end
  (`start >= duration`). The drop precedes the sequence check, so a ghost
  trailing real words cannot fail their ordering. Clocks malformed inside the
  window's domain — inverted bounds, non-finite values, unparsable shapes —
  still raise `WORD_CLOCK`/`WORD_SHAPE`, and in-window blank or out-of-order
  tokens still raise `WORD_SEQUENCE`. Clamping still never turns a malformed
  clock into plausible captured speech.
- The GPU window seam (`diarizer/batch_pipeline.py`) and the padded-retry
  adapter (`diarizer/batch_pipeline_models.recover_empty`) consume the same
  shared function, so a hallucinated clock entirely inside the left padding
  band now drops instead of failing the retry.
- The vendor lane (`utils/batch_pipeline/provider_stt.transcribe_async`) and
  the recovery lane (`utils/batch_pipeline/recovery_recognizers
  .validate_response`) validate responses through the shared function too:
  tail overshoot clamps into the capture, ghost clocks drop, and a response
  whose kept set is empty classifies as the honest `empty_asr` (or
  `MultilingualEmpty` for the multilingual recognizer) that the empty ladder
  already settles — instead of a `word_clock` invalid-response burn.

## Runbook

- `stage=word_clocks worker_reason=word_clock` quarantines should decay to
  the genuinely-malformed residue (inverted or non-finite model clocks inside
  the capture). A rate that does not decay after deploy points at a lane that
  was not migrated to the shared function.
- A unit that used to quarantine with `stage=word_clocks` may now surface as
  `empty_asr` when its hypothesis was ghost-only: that is the intended
  reclassification — the empty ladder (padded retry, strict-silence
  disposition, terminal-empty settlement) owns it from there.
- `response_validation`/`invalid_response` vendor failures persist only for
  genuinely malformed responses (reversed, non-finite, unparsable, blank,
  out-of-order clocks); a tail-overshoot-only response is now a clamped
  payload, not a failed attempt.
