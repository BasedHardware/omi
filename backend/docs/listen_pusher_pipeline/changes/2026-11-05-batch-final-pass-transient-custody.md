# Batch final-pass transient dependency custody

The initial batch speaker pass now defers transient Firestore/GCS and transport
failures into its existing speaker-only durable outbox. Retry deliveries use
the same classification, four-claim cap and jittered backoff. Persistent
transients close once as `skipped_retry_exhausted`; duplicate wakes cannot
reopen or count a closed obligation. No full-enrichment replay is introduced.

Unavailable, deadline, aborted, internal-server, quota/rate-limit, connection
reset and read-timeout failures defer as `deferred_transient`. Elapsed read
deadlines defer too. Unit/audio limits and object/byte caps remain terminal;
permanent authority/data failures do not defer. A permanent reload failure
closes as `failed_dependency`. Typed explicit causes survive reconstruction
wrappers and the batch diarizer boundary; arbitrary exception messages remain
excluded from diagnostics. Legacy diarizer lanes retain their fallback policy.

The owner lab captures retry requests without writes. No flag defaults,
production deadlines, slot waits or SDK retry loops change. See the
[harness instructions](../../../testing/owner_lab/README.md#batch-speaker-final-pass-repro).
