# Parakeet batch degenerate-normalization head-of-line poison

## The production signature

The parakeet container burns `normalize_batch` ValueErrors every day
(2026-10-28: 43, 2026-10-30: 99, 2026-11-01: 72, and the signature re-fired
2026-11-02 13:13 UTC). The raw line:

```
ValueError: normalize_batch with `per_feature` normalize_type received a
tensor of length 1. This will result in torch.std() returning nan. Make sure
your audio length has enough samples for a single feature (ex. at least
`hop_length` for Mel Spectrograms).
```

NeMo's per-feature normalization rejects the whole grouped GPU call when the
batch's shortest member is shorter than a single spectrogram frame — one
user's degenerate upload (most often a zero-second WAV) indicts the entire
batch.

## What was broken, for whom

`BatchEngine._flush_batch` (`backend/parakeet/batch_engine.py`) set that one
exception on EVERY future in the batch. Up to `max_batch_size` (32) healthy
user transcriptions failed because one user's upload was degenerate: the
other members were healthy files whose only fault was being batched with the
poison. Each event wasted a full GPU inference attempt on a batch it was
guaranteed to fail.

## The mechanism now

The flush path recognizes this input-shaped ValueError (exact message
prefix — see `_NORMALIZE_BATCH_ERROR`) when the failing batch holds more
than one file, and re-runs each file as its own GPU call
(`_retry_batch_one_by_one`):

- Healthy files still get their transcripts; no client-visible retry, no
  request loss.
- The genuinely degenerate file fails alone, with its own error — the
  upstream caller's existing single-file failure handling applies to exactly
  one user instead of a whole batch.
- A solo GPU call resolves its future with the per-file result list, so each
  request receives `results[0]` — the same per-file dict shape `submit()`
  always delivered; the raw list never leaks to callers.
- A single-file batch is already isolated and is never retried (the grouped
  call IS the solo call).
- A batch with any already-resolved future is never re-submitted (the split
  is one-shot per flush; shutdown prunes and deadline expiries are not
  outrun).
- Unrelated faults (generic ValueErrors, CUDA OOM, queue full) keep the old
  all-fail contract; OOM accounting and GPU-oom callbacks are unchanged, and
  the split path never books the OOM callback (it is not a GPU fault).
- File cleanup stays with the flush's `finally` (`owns_file`); the retry
  never unlinks audio itself, so a failed split retry still cleans up.
- Cancellation during the split retry resolves every outstanding future with
  the shutdown error before propagating, matching the grouped-call cancel
  path.
- Queue-wait accounting fires once per file at flush selection, before any
  GPU work, so solo retries never double-report queue waits; the failed
  grouped call still reports no batch completion (same as before).

## Observability

`BatchEngine.metrics["degenerate_batch_split_retries"]` counts flushes that
took the split path (exposed with the rest of the engine metrics on the
service's metrics surface). A steady nonzero value means degenerate uploads
are still arriving upstream (clients or upload paths producing sub-frame
audio); the per-batch WARNING line names how many files were re-run. The
durable goal stays upstream prevention of degenerate uploads; this boundary
stops them from taking other users' transcriptions down with them.

## Failure class

`FC-batch-fault-domain-head-of-line-poison` — one malformed item must not
roll back later independent items in an ordered batch. Regression suite:
`backend/tests/unit/test_parakeet_batch_degenerate_poison.py` (RED on the
parent for the poison contracts: on the previous code the grouped failure
set the normalization ValueError on every future and the split metric never
moves).
