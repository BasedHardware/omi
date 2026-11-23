# v3 outline: provider 5xx answers the retryable contract

SCA-3170. A transient gateway 5xx on the v3 conversation-outline call used to
escape the Cloud Tasks builder route as an unhandled 500 (prod group
`CIqco6zElomJFg`, 243 events/24h). The outline call keeps `max_retries=0` and
its 30s `request_timeout`; the failure is now classified at the boundary.

- The `reconcile` and `backfill` task routes answer a provider/transport
  failure with the existing retryable contract: 503 + `Retry-After: 2` + the
  typed `conversation_processing_retryable` detail. Cloud Tasks retries the
  task (`conversations-v3` `max_attempts: 10`, 30-300s backoff).
- An already-typed `HTTPException` from the composition boundary is re-raised
  unchanged, so its metric is recorded once and a deliberate non-retryable
  answer is not overridden.
- The shared background-task done callback logs a transient provider fault as
  one bounded WARNING with the failure class only, not the provider body at
  ERROR. This covers the paid outline task and the on-open reconcile task.
- A non-provider failure keeps its loud 500 and ERROR log.

Kill switch: `CONVERSATION_PROCESSING_RETRYABLE_PROVIDER_FAILURE_ENABLED`
(default on). Off restores the previous generic 500. No schema or stored-state
change; the gateway circuit/fallback behavior is unchanged.

See the [conversation lifecycle contract](../../listen_pusher_pipeline.mdx).
