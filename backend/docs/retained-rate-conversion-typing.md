# The retained rate cohort joins the typed decode-custody family

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder

The GPU worker's fetch_decode boundary classifies every deterministic decode
fault by type: the raise sites carry a typed custody fault (`StagedAudioInvalid`,
`StagedArtifactInvalid`, `RetainedAudioInvalid`, `DecodedDurationMismatch`) and
the boundary reads the type, ends the GPU chain and hands the unit to the fenced
recovery lane with its measured VAD evidence intact. One raiser still escaped
that contract: `decode_source`'s sample-rate conversion. A retained reference
whose stored `sample_rate` was never an integer — `'16000.0'`, `'16 kHz'`, `''`,
`None`, `NaN`, bytes, containers — raised a bare `ValueError` (or `TypeError`,
or `OverflowError` for infinite floats) instead of a family member, so the
boundary booked the unit `reason=unclassified`, the scheduler walked the bounded
retry ladder on identical pinned bytes (max_attempts GPU passes per segment),
and the sensor saw the anonymous `error_class=ValueError stage=fetch_decode
reason=unclassified` cohort with no family token to route on.

## What changed

- `utils/batch_pipeline/source_audio.py`: the sample-rate conversion raises
  `RetainedAudioInvalid('invalid retained PCM')` for every non-integer stored
  rate. The message and token are the same ones the existing bounds fault uses,
  so `proof_reason`'s exact-message table and every downstream map keep working
  unchanged; the conversion context is suppressed (`from None`) because the
  underlying `int()` failure adds nothing the closed token lacks. Valid shapes
  keep converting exactly as before: ints, numeric strings, digit bytes,
  integral floats, and unicode-digit strings that `int()` accepts.
- No boundary, scheduler, predicate, custody or recovery change: the fault
  already rides the landed `retained_audio_invalid` arm — terminal
  `ValidationFailureWork`, quarantine on attempt one with `recovery_state=held`,
  the demoted INFO log line, and the fenced independent-recognizer lane waiting
  below. The fix is purely at the raise site, exactly the contract the module
  docstring already states ("raise sites carry the type and the worker boundary
  reads the type — never an exception message — so a new deterministic decode
  fault cannot silently drift back onto the ladder").

## Unchanged accounting

- Retryable retained faults stay retryable: `RetainedAudioOutsideAdmittedSource`
  and every non-family exception keep their ERROR lines and the ladder.
- The raw-live and opus decoders return their own 16 kHz output before the
  plain-PCM rate conversion; stored rate metadata does not gate them, and the
  grid pins that path gating explicitly.
- `proof_reason('invalid retained PCM')` still maps to `decode_or_checksum`.

## Verification

- `tests/unit/test_retained_rate_conversion_grid.py` pins every stored-rate
  shape through the real `decode_source` on all four source paths.
- `tests/unit/test_retained_conversion_boundary_grid.py` drives the real worker
  boundary: typed faults end the chain terminal, the anonymous negative space
  stays on the ladder, and each log channel keeps its event and severity.
- `tests/unit/test_retained_conversion_custody_grid.py` books every closed
  (stage, reason) diagnosis through the real scheduler: durable rows, the
  demotion families' INFO channels, the awaiting-fenced-recovery warning and
  the ladder economics the anonymous cohort still pays.
- `tests/unit/test_retained_conversion_predicate_grid.py` pins the closed
  demotion predicates over their full stage/reason/switch vocabulary.
- `tests/unit/test_retained_conversion_downstream_maps.py` pins the
  `proof_reason` table, tail-gap buckets and the `site=` attribution field.
- `tests/unit/test_batch_pipeline_retained_audio_invalid.py` gains the
  conversion cohort's raise-site and worker-boundary cells.
