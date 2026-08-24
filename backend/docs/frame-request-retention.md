# Frame-request pixel retention

Frame pixels use two physically separate storage tiers. `BUCKET_FRAME_REQUESTS_TEMPORARY`
has a six-day `Delete` lifecycle rule and soft delete disabled, so scheduler
downtime cannot retain unattached pixels for seven days. `BUCKET_FRAME_REQUESTS`
has no object-expiration rule: conversation-attached objects are permanent for
the lifetime of their conversation. Attachment first reserves a permanent
cleanup receipt, copies the temporary object into the permanent bucket, and
then atomically changes the conversation photo and request metadata to the
permanent storage ID. A retryable receipt removes the displaced temporary copy.

Requested/claimed/uploaded objects are also removed eagerly by the scheduled
retention worker after their Firestore row reaches a terminal cleanup state.
An uploaded request without a conversation remains temporary and is available
to authenticated JIT vision through its owner- and generation-fenced temporary
image endpoint; reading it never promotes it or extends its expiry. The backend
agent's `look_at_frame` consumer accepts only a screen evidence reference
admitted in that request and reserves a request-scoped one-frame budget before
queueing or invoking vision. Its telemetry contains only closed outcome and
vision-invoked fields, never frame IDs, OCR, pixels, or descriptions.

The worker retries external deletion independently of queue delivery and the
rollout kill switch. Per-account retries and population scans have independent
cursors and finite page budgets, so a poison account cannot pin the population
scan. Cleanup operations are idempotent under overlapping executions. Account
deletion enumerates all queue pages, deletion outbox entries, and photo
subcollections before deleting opaque objects. Conversation deletion persists
an object-deletion outbox before deleting conversation metadata, so an external
storage failure remains recoverable. An attached permanent object is never
selected by temporary-request cleanup.

Deployment evidence must include both exact bucket names, the permanent
bucket's absence of an object-expiration lifecycle rule, the temporary bucket's
six-day delete rule and zero-second soft-delete policy, and both runtime env
bindings. This source tree does not mutate GCP; the live predeploy receipt is an
integration gate.

Run the source-only check with `python backend/scripts/validate_frame_request_bucket_contract.py
--source-only --runtime-env backend/deploy/runtime_env.yaml --contract
backend/deploy/frame-request-bucket-contract.json`. Deployment must additionally
pass the workflow's live `gcloud storage buckets describe` validation for both
buckets' exact identity, location, tier-specific lifecycle, soft-delete,
uniform bucket-level access, public-access prevention, and encryption posture.
Runtime-env-only validation cannot claim the live bucket gate. The independent
`frame-request-retention-hourly` Scheduler target is also a deployment gate; it
does not share the canonical memory-maintenance schedule. Until operators set
`FRAME_REQUEST_RETENTION_INDEPENDENT_HEALTHY=true` after observing that job,
memory maintenance retains its legacy cleanup call as a rollback-safe bridge. The
desktop `device_id` is an owner-scoped routing and recovery identifier, not a
standalone credential: Firebase authentication, account generation, and exact
device matching remain authoritative. The current product does not claim
cryptographic device authentication; strengthening that boundary is a separate
security decision.

User exports include frame-request metadata and explicit conversation-photo
manifests. When the dedicated object is readable, the manifest carries
`bytes_base64`; if it is unavailable, `bytes_available: false` makes that
limitation explicit rather than silently omitting the image.
