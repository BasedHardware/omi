# Batch pipeline: permanent retained-audio decode failures

A retained audio unit whose stored bytes can never decode fails identically on
every retry: the manifest pins object generations, so a retry re-reads the same
bytes. These failures are typed at the read boundary
(`utils/batch_pipeline/source_audio.py::RetainedAudioInvalid`) and carry the
closed reason `retained_audio_invalid` (plus `decoded_duration_mismatch` for the
deterministic decoded-extent-versus-admitted-capture disagreement) through the
GPU worker, the scheduler, the shadow CAS and the fenced recovery lane.

## What changed

- `decode_source` / `read_reference` / `materialize` / `ArtifactStore.fetch_audio`
  raise `RetainedAudioInvalid` (a `ValueError` subclass) for the permanent
  decode family: invalid size, truncated or invalid encrypted frame, failed
  AES-GCM authentication, retained capture checksum mismatch, invalid retained
  PCM, oversize source, digest drift, malformed manifests
  (`InvalidRetainedManifest` is now a subclass), opus/capture decoder ValueErrors.
- The diarizer worker classifies these at `fetch_decode` into
  `ValidationFailureWork` with the closed reason. The scheduler quarantines on
  the first attempt (`worker_failure` evidence), so the bounded retry ladder
  (default `max_attempts=5` GPU cycles per segment) is no longer walked on
  identical bytes, and `batch_worker_failed` logs once per segment instead of
  once per attempt.
- The fenced recovery lane holds these units once
  (`failed_held`, refusal reason `retained_audio_invalid`) instead of re-reading
  the same bytes on every recovery sweep. The bucket-allowlist ValueError stays
  retryable by design: the allowed set is deploy configuration, not data.

## Runbook

- A spike of `event=batch_worker_failed error_class=RetainedAudioInvalid
  stage=fetch_decode reason=retained_audio_invalid` means clients or intake are
  producing stored audio that cannot decode; group by reason to find the class
  (checksum mismatch vs authentication failure vs invalid PCM).
- Quarantined units with `worker_failure.reason=retained_audio_invalid` are
  held for the privacy-fenced recovery path; they are not GPU-retryable and
  never will be — investigate the upload path, not the GPU pool.
- `reason=decoded_duration_mismatch` points at admission metadata disagreeing
  with stored bytes (intake stamping bug or truncated upload), not at decode
  corruption.
