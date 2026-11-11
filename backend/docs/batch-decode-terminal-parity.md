# Batch decode terminal parity

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

A staged unit whose pinned bytes can never decode used to reach the
fetch_decode boundary as an ordinary exception. The boundary recognized
only a hand-written list of exception messages (three staged-audio
strings) plus the retained-audio type, so every other deterministic decode
fault — a garbage WAV container refused by `wave`, a NaN float in the
frozen intake context that `json.dumps` refuses, an envelope that fails
the bounded-context guard — fell through as an unclassified `ValueError`,
joined the ordinary retry ladder, and burned all five GPU attempts on
bytes that fail identically every time before quarantining blind. In
production this surfaced as the `event=batch_worker_failed
error_class=ValueError stage=fetch_decode` signature, four wasted GPU
attempts per stuck unit, and a terminal quarantine whose evidence names
neither the fault nor its determinism.

## What changed

- The deterministic decode faults now carry a type instead of relying on
  message matching:
  - `utils.batch_pipeline.audio.StagedAudioInvalid` — staged or derived
    audio that can never decode from these pinned bytes. Raised by
    `decode_pcm16_wav` for the staging-format, length and truncation
    guards, for garbage or header-truncated WAV containers (`wave.Error`,
    `EOFError`, `struct.error`), and by `with_context` for the bounded
    intake-context envelope (including a non-serializable float in the
    stored context).
  - `diarizer.batch_pipeline.DecodedDurationMismatch` — decoded extent
    disagreeing with the admitted capture extent.
  - Both are `ValueError` subclasses, so every existing
    `except ValueError` caller (the CPU recovery lane, the flight
    qualifier, the benchmark harness) keeps catching them unchanged.
- The worker's fetch_decode boundary reads the types and never exception
  messages. The closed reason vocabulary is unchanged: the faults still
  quarantine as `staged_audio_invalid` and `decoded_duration_mismatch`
  with the same durable `{'stage', 'reason'}` evidence, the same
  `ValidationFailureWork` handoff, and the same held-recovery custody as
  before. Only the classification input changed.
- Untyped exceptions at the boundary keep the legacy behavior exactly:
  an ordinary `ValueError`, `wave.Error` raised by a non-decoder
  callable, or a `RuntimeError` still produces retryable `FailedWork`
  (with its stage/reason evidence from the failure-evidence chain) and
  still walks the bounded ladder. Intentionally retryable retained-audio
  refusals — a bucket outside the deployed allowlist, a storage fault —
  stay plain and retryable.

## Why typed sites and not a longer message list

Message matching drifts: the next deterministic decode raise site (and
the next staging guard) silently joins the ladder again, and the only
signal is the error signature burning in production. With the type at
the raise sites and the boundary reading the type, a new deterministic
fault is terminal by construction, and the parity suite pins every
raise site and every boundary mapping so the two cannot drift apart.

## Verification

`backend/tests/unit/test_staged_audio_decode_terminal_parity.py` pins
the decoder and envelope raise-site matrix;
`test_fetch_decode_typed_boundary_parity.py` pins the boundary mapping
and its stage scoping; `test_staged_audio_ladder_stop_parity.py` pins
the attempt economics (terminal at attempt 1, ladder parity for untyped
faults); `test_staged_audio_recovery_hold_parity.py` pins the recovery
and custody semantics of the typed quarantines.
