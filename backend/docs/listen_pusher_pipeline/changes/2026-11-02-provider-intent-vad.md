# Durable provider VAD evidence

The [batch pipeline](../../listen_pusher_pipeline.mdx) provider stage now saves
`provider_intent.measured_vad_speech_seconds` with the pending-to-running CAS,
before the paid vendor call. Terminal held settlements reuse that strict-VAD
measurement through the existing cumulative held-VAD census, including when
reconciliation abandons an intent after 900 seconds. Reconciliation performs no
extra audio fetch or inspection. Old intents without the field retain unknown
VAD behavior; missing evidence never becomes measured silence.

This is on with the provider stage and requires the backend-sync worker release.
It changes no observer, hard-3 threshold, routing flag, paid-attempt bounds, or
recovery eligibility. Abandoned attempts can already fail over when a configured
route table is armed and admits an unspent alternate vendor. A terminal
`failed_held` provider unit remains outside quarantine recovery.

Synthetic regressions in `tests/unit/test_batch_provider_stt.py` cover pre-call
persistence, stored and legacy abandoned intents, zero speech, duplicate
delivery, a losing intent CAS, and cumulative evidence in both terminal paths.
