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
An uploaded request without a conversation remains temporary. Retired JIT
vision consumers no longer read or promote these pixels; existing frame-request
metadata and objects stay subject to the retention, export, and account-deletion
paths below. Reading a retained request never extends its expiry.

Completed desktop conversations persist a metadata-only keyframe outbox intent
independently of rollout availability. Finalization, later screen sync, and the
hourly recovery worker can reconcile it. Selection queries the exact device,
account generation, and conversation time window newest-first, requires the
Mac's fail-closed Rewind-exclusion attestation, and uses the authoritative local
screenshot ID. Upload decoding strips metadata and canonicalizes JPEG/PNG/WebP
to a bounded JPEG before storage or vision. The existing desktop recovery loop
uploads and promotes the winner; missing/aged local captures terminalize as
pruned without blocking the text conversation.

The worker retries external deletion independently of queue delivery and the
rollout kill switch. Per-account retries and population scans have independent
cursors and finite page budgets, so a poison account cannot pin the population
scan. A durable generation-fenced lease prevents overlapping workers from
regressing either cursor; lease expiry recovers a crashed worker. Account
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
is the sole retention owner since memory-maintenance-job (whose legacy cleanup
call once bridged this job) was retired on 2026-10-26. The
desktop `device_id` is an owner-scoped routing and recovery identifier, not a
standalone credential: Firebase authentication, account generation, and exact
device matching remain authoritative. The current product does not claim
cryptographic device authentication; strengthening that boundary is a separate
security decision.

User exports include frame-request metadata, durable vision/keyframe receipts,
and explicit conversation-photo manifests. When the dedicated object is readable, the manifest carries
`bytes_base64`; if it is unavailable, `bytes_available: false` makes that
limitation explicit rather than silently omitting the image.
