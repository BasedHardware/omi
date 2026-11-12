# 2026-11-12 Intake envelope typed boundary

`read_context` in `utils/batch_pipeline/audio.py` joined the family
doctrine: its four envelope faults (plus corrupt/pathological JSON in the
sealed chunk) now carry `StagedAudioInvalid` instead of bare `ValueError`.
`read_context` was the last intake-envelope reader whose raise sites stayed
anonymous; every other decoder in the batch family
(`decode_pcm16_wav`, `with_context`, `capture_decode`, `source_audio`)
already types its deterministic faults.

Caller behavior is unchanged: the type is a `ValueError` subclass, so the
worker's fail-open context swallow, the projection payload-contract catch,
and the coverage/manifest best-effort readers all keep catching these
faults. What changes is what the boundaries can name: worker fetch_decode
evidence, the terminal worker-validation disposition, and the projection
payload contract now see the typed family instead of the anonymous
`error_class=ValueError` vocabulary that prod books for
`stage=fetch_decode` — the same cohort the sensor lists as a top signature.

Contract and verdict table: `backend/docs/intake-envelope-typed-boundary.md`.
Grids: `backend/tests/unit/test_intake_envelope_*_grid.py`,
`backend/tests/unit/test_intake_context_typed_boundary.py`.
