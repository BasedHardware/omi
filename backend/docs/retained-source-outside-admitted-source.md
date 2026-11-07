# Retained fetch faults carry closed names end to end

The GPU worker's `fetch_decode` boundary had one anonymous fault class left: a
retained manifest whose reference names a bucket this deployment does not
admit raised a bare `ValueError` (`utils/batch_pipeline/source_audio.py`,
`validate_reference`). Every other fault on that boundary — staged WAV shape,
staged artifact envelope, retained bytes, decoded-duration mismatch, the
word/VAD validation family — is typed and carries a closed reason token. The
anonymous one collapsed the whole cohort into
`error_class=ValueError reason=unclassified` per-attempt records and
`stage=unknown worker_reason=unclassified` terminal quarantines (the loop
sensor's #4 signature at x386/30m on 2026-11-07): operators could not tell a
bucket-config mismatch from any other bare fault, and the terminal record
could not name what burned the ladder even when earlier attempts had carried
the diagnosis.

## What changed

- `validate_reference` raises `RetainedAudioOutsideAdmittedSource` — typed,
  still a plain `ValueError`, deliberately **not** a `RetainedAudioInvalid`
  subclass. The fault stays retryable exactly as documented before: the
  admitted bucket set is deploy configuration, not manifest data, so a later
  deploy can admit the reference and the bounded ladder keeps walking. The
  type exists so the worker evidence, the per-attempt failure record and the
  terminal quarantine can name `outside_admitted_source` (new
  `WorkerValidationReason` token) instead of `unclassified`.
- `validate_reference`'s generation guard admits ASCII digits only. The
  former `str(generation).isdigit()` accepted unicode digits (`'²'`) that
  `int()` then rejected with a second anonymous bare `ValueError` past the
  validator; that manifest shape is now `InvalidRetainedManifest` (the
  manifest-can-never-materialize family, terminal at fetch_decode on the
  first attempt). JSON-number generations (`"generation": 7`) remain
  admitted, as before.
- The scheduler's terminal quarantine record reads the ladder's accumulated
  diagnosis. The commit already preserved each attempt's evidence on the job
  ("a later attempt without evidence preserves the previous diagnosis"), but
  the log line only looked at the current attempt's locals — so an
  evidence-less exhausting attempt (a missing worker result, an untyped
  stage) logged `unknown/unclassified` even though the job doc carried
  `fetch_decode/outside_admitted_source`. The record now prefers the current
  attempt's structured failure, then its evidence, then the preserved
  diagnosis. A never-diagnosed unit still records the historical
  `unknown/unclassified` shape.
- `restore_audio_in_transaction` and `redrive_in_transaction` clear a stale
  diagnosis when they requeue a unit (`complete` already did): a fresh
  ladder collects its own diagnosis and must not inherit the previous
  epoch's stage/reason.

## Contracts that do not change

- Retry semantics: an outside-admitted-source fault rides the same bounded
  ladder as before (defer, backoff, max-attempts). No unit quarantines
  earlier, and no fault ends the chain that did not end it before — except
  the unicode-digit generation shape, which was never admit-able (it crashed
  `int()` every attempt) and is now terminal on the first attempt like its
  sibling manifest faults.
- The `safety-net` / recovery / disposition gates, the padded-retry ladder,
  word ownership and silence disposition are untouched.
- Closed vocabulary is additive: one new reason token; no token moved or
  changed meaning; the evidence gate remains the terminal gate plus
  `unknown`.

## Operator note

A unit whose evidence or terminal record names
`outside_admitted_source` (stage `fetch_decode`) means its stored manifest
references a bucket outside the deployment's admitted set —
`BUCKET_PRIVATE_CLOUD_SYNC` plus `BUCKET_AUDIO_DERIVED` on the batch
pipeline worker. Fix the deployment env (or the producer writing the
manifest), not the bytes: the references are generation-pinned and will
decode unchanged once admitted. The unit recovers on its next ladder attempt
without any data repair.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
