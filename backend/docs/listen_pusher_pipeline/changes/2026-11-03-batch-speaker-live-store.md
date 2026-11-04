# Batch speaker windows require admitted timing provenance

A `final:batch:{unit}` scope can come from live pusher custody or a `batch_sync_v1` WAL upload;
record-origin does not prove the live clock. This corrects the original scope-only selection in #24465.
CPU admission records optional `WorkItem.timing_store` from the actual source: built-in WAL decoding uses
`sync`; retained live manifests use `batch` only when every reference is `.batch.enc` / `.batch.bin`.
Unknown/mixed references and alternate decoders remain unstamped. Projection copies the stamp into the
storage-only `provider_speaker` dict with the original scope/id/provider; all survive conversation
re-scoping. Public JSON still omits that dict.

Timing provenance also survives conversations above the grouping sidecar's 256-entry or aggregate
byte limit. On overflow, storage retains only a compact, encrypted provider partition and timing
stamp per segment, with a 1 KiB plaintext / 2 KiB encrypted per-marker limit. Reads authenticate
and bind each marker to its segment before exempting it from the conversation limits. Other
grouping metadata keeps its existing bounds; malformed, missing or unauthenticated stamps fail closed.
The regression persists 2,100 segments across seven units and proves each window on its stamped store.

Only stamped `final:batch:` windows refused for overlapping stores can be proven on the named store.
Sync stamps select `.opus` / `.opus.enc`; batch stamps select `is_batch` / `.batch.enc` / `.batch.bin`.
Proof, decoded coverage and clip assembly use the same store without fallback. Unstamped history stays
refused: job `audio_uri` points to a generic staged artifact and cannot prove its source cheaply. No
historical lookup/backfill or privacy contract changes are added.

`SPEAKER_BATCH_STORE_ENABLED` defaults on inside the per-window cohort and controls stamped batch-scoped
windows on either store. False/0/off/no restores their refusal independently of `SPEAKER_SYNC_STORE_ENABLED`,
which controls native `sync:` scopes. Manual receipts and naming/budget policy are unchanged.
The log is now `conversation_speaker_store` with candidates, total proven, `batch_proven` and `sync_proven`;
repository charts, monitoring and scripts had no references to its previous name.

Contract: [trusted placement](../../listen_pusher_pipeline.mdx#trusted-capture-span-placement-and-live-speaker-resolution).
Operations: [batch speaker runbook](../../runbooks/batch-conversation-speakers.md).
Regression evidence: store and producer suites cover WAL/live selection, unstamped refusal, admission
provenance, re-scoping, holes, kill switches and manual precedence. No GPU worker, streaming or deployment
change is included. Local synthetic tests establish store isolation and identity policy; real-audio
attribution accuracy remains a separate measurement.
