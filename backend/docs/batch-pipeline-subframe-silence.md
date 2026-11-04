# Batch pipeline: sub-frame captures dispose through strict VAD first

A capture shorter than one complete Silero frame — 512 samples at 16 kHz,
the recovery lane's `SILENCE_THRESHOLD_SECONDS` — cannot contain measurable
speech. The model VAD's padded frames can only fabricate spans that start
beyond the buffer on such input: the deterministic `vad_bounds` raise whose
disposition branch re-derives the same answer from the strict CPU
inspector, and whose quarantined units then burn a fenced recovery sweep
that settles them with the recovery lane's own below-frame rule.

## What changed

- The GPU worker's `vad_windows` stage asks the strict CPU inspector first
  for sub-frame captures (`below_silence_threshold`), exactly like the
  language-blocked path already does. Strict silence disposes the unit as
  silence with no pyannote forward and no quarantine hop. Strict speech or
  unavailable evidence keeps the existing flow unchanged: the model call
  for a non-excluded unit, the language barrier raise for an excluded one.
- The strict-inspector-first arm reuses the recovery lane's
  `below_silence_threshold` rule as its single source of truth, so the
  worker's disposition and the recovery lane's independent silence rule
  cannot disagree at the 512-sample boundary.
- Silence payloads keep the established `words_provider=strict_local_vad`
  marker, so downstream terminal-empty and held-disposition readers see
  the evidence source, not the untouched word provider.

## Contracts that do not change

- Framed captures (512 samples and up) keep the model-VAD-first contract;
  the `vad_bounds` disposition branch and its rollback arms are untouched.
- The anti-fabrication invariant holds: silence is still established by a
  VAD measurement (the strict inspector), never inferred from duration
  alone. A strict speech claim on a sub-frame buffer continues to hold the
  unit through today's vad_bounds path.
- The `worker_validation_disposition_enabled` and
  `BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED` flags keep their meanings;
  the sub-frame arm runs before both and changes only which inspector is
  consulted first for degenerate-length audio.

## Runbook

- A `vad_bounds` quarantine spike means framed audio with out-of-buffer
  model frames whose strict inspector could not establish silence; it is
  not a decoder or intake regression. Sub-frame captures no longer appear
  in that population.
- `words_provider=strict_local_vad` silence outcomes for very short
  captures are the strict-inspector disposition, not lost audio: a capture
  shorter than one VAD frame has no measurable speech to transcribe.

Failure-Class: FC-subframe-capture-burns-model-vad-and-fenced-recovery-hop
