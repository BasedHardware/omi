# Retained decode fault typing at the fetch_decode boundary

## What this changes

Every deterministic decoder fault on the pinned retained-audio bytes now ends
the GPU chain typed as `retained_audio_invalid` instead of escaping
`decode_source` as a bare non-`ValueError` that rode the bounded retry ladder
anonymously.

The retained decode arms (`raw-live` capture decode, legacy `.opus`, and the
canonical PCM resample tail) wrapped only `ValueError`. Faults the decoders
raise outside that class — `opuslib.OpusError` from corrupt WAL packets,
`KeyError` from stored metadata missing `sample_rate`/`channels`/`format`,
`audioop.error` from the resampler, `struct.error`, `ZeroDivisionError` from
a stored `channels: "0"`, `OverflowError` from an absurd stored rate, and
pydub's `CouldntDecodeError` — escaped to the worker fetch_decode boundary as
anonymous faults. The worker booked them `reason=unclassified`, the scheduler
walked the full five-attempt GPU ladder on identical pinned bytes (every
attempt re-downloads and re-decodes the same generation), and the terminal
quarantine logged `stage=unknown worker_reason=unclassified` — the production
signature family that could not be told apart from any other bare fault.

The wrap sites now convert exactly the `decoder_fault_types()` tuple:
`ValueError, KeyError, TypeError, struct.error, audio.op.error, CouldntDecodeError,
ZeroDivisionError, OverflowError`, plus the native opus binding's `OpusError`
when the binding resolves on the host. `RuntimeError` is deliberately absent:
the binding raises it when libopus itself is missing, which is a deploy
configuration fault rather than a bytes fault and must stay loud and
unclassified.

## What stays the same

- Durable custody, evidence, metrics, and the awaiting-fenced-recovery
  warning are unchanged; only the fault classification and the ladder walk
  differ.
- `ValueError` keeps its historical message pass-through; converted faults
  chain their cause. The boundary reads the type, never the message, and no
  message reaches a log line.
- The deliberately-retryable `outside_admitted_source` and every genuinely
  unclassified fault keep their retry semantics and ERROR lines.
- The typed trio (staged/retained/decoded-extent) already ended the chain
  unconditionally and demoted at the scheduler; the new classes join that
  existing route with no new plumbing.

## Failure-Class

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder

A deterministic decoder fault that escapes the typed boundary burns the
bounded retry ladder on identical bytes and quarantines unclassified.

## Tests

The parity suites in `tests/unit/test_retained_*` pin, per fault class and
per arm: the typed conversion and cause chaining, the pass-through of
`RuntimeError`, the fault-tuple membership and its binding conditionality,
worker custody (`ValidationFailureWork`, closed evidence, attempt-one
quarantine, no re-pull), the scheduler ladder parity against the untyped
cohort, and the surrounding envelope/manifest/WAL/reference contracts the
decode path depends on.
