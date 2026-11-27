# v3 outline: preserve mobile and Cloud Tasks retry contracts

SCA-3170. A transient gateway 5xx on the v3 conversation-outline call used to
escape the Cloud Tasks builder route as an unhandled 500 (prod group
`CIqco6zElomJFg`, 243 events/24h). The outline call keeps `max_retries=0` and
its 30s `request_timeout`; the failure is now classified at the boundary.

- Synchronous mobile requests keep the typed 503 + `Retry-After: 2` +
  `conversation_processing_retryable` answer. The `reconcile` and `backfill`
  Cloud Tasks routes translate that retryable provider answer to HTTP 409
  `dependency_warming`, which uses the owning queue's configured backoff. Cloud
  Tasks ignores `Retry-After` and fast 5xx answers can throttle the queue.
- A typed retryable 503 from the composition boundary is translated without
  recording its metric twice. Other typed HTTP answers pass through unchanged.
- Owner-busy on native manual-ready reconcile and backfill answers HTTP 409
  `locked`. Ordinary background reconcile keeps its HTTP 200 `busy` outcome,
  because another active pass owns the work.
- The `v3-paid-work` and `v3-reconcile-open` background tasks opt into bounded
  provider-failure logging: a transient provider fault is one WARNING with the
  failure class only, not the provider body at ERROR. The opt-in is limited to
  tasks whose caller owns a queue retry; every other background task keeps its
  loud ERROR so Error Reporting still sees it.
- A non-provider failure keeps its loud 500 and ERROR log.

Kill switch: `CONVERSATION_PROCESSING_RETRYABLE_PROVIDER_FAILURE_ENABLED`
(default on). Off restores the previous generic 500 for classified provider
failures; synchronous callers no longer receive the retryable 503 and Cloud
Tasks routes no longer translate those failures to `dependency_warming`. No
schema or stored-state change; the gateway circuit/fallback behavior is unchanged.

See the [conversation lifecycle contract](../../listen_pusher_pipeline.mdx).
