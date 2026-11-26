# Provider STT retries after Firestore contention

SCA-2625 routes an expired or contended Firestore transaction in the provider-STT
stage through the existing HTTP 409 retry response. Settlement releases the
outbox lease when it still belongs to that delivery. Redelivery consults the
durable provider intent and reuses an available result artifact, so a
transaction failure does not authorize another paid call.

The change preserves the existing privacy checks, intent and outbox ownership
fences, and retention rules. It adds no stored fields or rollout flag. See the
[provider-STT serving contract](../../batch-pipeline-serving.md) and
[runtime tests and emulator evidence](https://github.com/BasedHardware/omi/pull/26162).
