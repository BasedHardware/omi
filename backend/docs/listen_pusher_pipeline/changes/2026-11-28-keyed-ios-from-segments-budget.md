Keyed iOS uploads share one 25-second HTTP budget across auth, intake and the
wait for processing. A worker that starts within that budget has up to 300
seconds for the existing processing stages. It keeps its processing claim if
the HTTP wait expires. A retry sees a retryable 503 while the claim is active
and a 200 with the stored result after completion.

With the continuation rollout off, these uploads use the synchronous notes
path on a separate executor with four workers and four queue slots. Queued
work must start before the HTTP deadline to acquire a claim. This keeps long
iOS notes calls from occupying the pool used by other from-segments uploads.
The serving revision needs CPU between requests. The existing rollout mode
still controls the async notes path.

A retryable notes dependency failure or processing budget cut releases the
existing claim for readmission with its stored transcript. A stale claim
can be reclaimed only if the lease observed at intake still matches. The
`from_segments_503` log reports `raise_site` and, when available,
`failure_class`. A `request_budget_exhausted` site identifies a budget cut.
A `conversation_processing_retryable` site with `failure_class=timeout`
identifies a dependency timeout.

The `from_segments_timing` INFO event records monotonic millisecond offsets
from route entry for intake, notes, persistence, and HTTP exit. Every
classified attempt emits an `http` record. A worker that finishes after HTTP
exit emits one additional `worker` record with the original HTTP status and
available stage offsets. Use `http` records for attempt counts and `worker`
records for late stage timings. Each record contains only a closed client
kind, the keyed boolean, status, and timing fields. Auth, rate-limit, and
validation refusals before the parsed key is available use the existing route
telemetry.

Release owns admission and rollback. SCA-3846 owns the production measurement
of valid-attempt 503s, a previously cut retry returning 200, and two passing
health ticks. See the [pipeline contract](../../listen_pusher_pipeline.mdx#continued-ios-from-segments-processing).
