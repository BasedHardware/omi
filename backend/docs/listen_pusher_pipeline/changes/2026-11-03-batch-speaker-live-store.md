# Prove batch speaker windows on the live store

Persisted `final:batch:{unit}` speaker scopes originate in desktop record units timed on the live store.
When overlapping live and sync spans cause `untrusted_clock`, the per-window resolver now proves these
windows against `is_batch` / `.batch.enc` / `.batch.bin` chunks alone. Both decoded-window verification and
embedding clip assembly select that store. A missing, malformed, overlapping or uncovered live span still
refuses proof; sync audio never fills a live-store hole. Resolved conversation scopes require the retained
unit scope in `provider_speaker` to recover the timing store.

`SPEAKER_BATCH_STORE_ENABLED` defaults on, independently of `SPEAKER_SYNC_STORE_ENABLED`; false/0/off/no
restores the previous batch refusal. It follows the existing per-window cohort, with no additional admission
or deployment in this change. The existing `conversation_speaker_sync_store` log reports total candidates,
total proofs and `batch_proven`. Manual receipts retain precedence.

Contract: [trusted placement](../../listen_pusher_pipeline.mdx#trusted-capture-span-placement-and-live-speaker-resolution).
Operations: [batch speaker runbook](../../runbooks/batch-conversation-speakers.md).
Regression evidence: `backend/tests/unit/test_speaker_sync_store.py` covers two-store live-only reads,
rollback, local holes, retained provider scopes and manual overrides. The producer, GPU worker, streaming
path and voice-vector privacy contract are unchanged. Local synthetic tests establish store isolation and
identity policy; real-audio attribution accuracy remains a separate measurement.
