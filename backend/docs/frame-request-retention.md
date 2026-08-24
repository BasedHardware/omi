# Frame-request pixel retention

`BUCKET_FRAME_REQUESTS` is a dedicated runtime binding. It must point at a
bucket whose lifecycle policy does not expire objects: conversation-attached
objects are permanent for the lifetime of their conversation. Temporary
requested/claimed/uploaded objects are removed by the scheduled retention
worker after their Firestore row reaches a terminal cleanup state. An uploaded
request without a conversation remains temporary (at most seven days) and is
available to authenticated JIT vision through its owner- and generation-fenced
temporary image endpoint; reading it never promotes it or extends its expiry.

The worker retries external deletion independently of queue delivery and the
rollout kill switch. Account deletion and conversation deletion enumerate all
queue pages and photo subcollections before deleting opaque objects; an
attached object is never selected by temporary cleanup.

Deployment evidence must include the bucket name, the absence of an object
expiration lifecycle rule, and the runtime env binding. This source tree does
not mutate GCP; the deploy receipt is an integration gate.

Run the source-only check with `python backend/scripts/validate_frame_request_bucket_contract.py
--source-only --runtime-env backend/deploy/runtime_env.yaml --contract
backend/deploy/frame-request-bucket-contract.json`. Deployment must additionally
pass the workflow's live `gcloud storage buckets describe` validation for exact
bucket identity, location, no-expiry lifecycle, uniform bucket-level access,
public-access prevention, and encryption posture. Runtime-env-only validation
cannot claim the live bucket gate. The independent
`frame-request-retention-hourly` Scheduler target is also a deployment gate; it
does not share the canonical memory-maintenance schedule. The
desktop `device_id` is an owner-scoped routing and recovery identifier, not a
standalone credential: Firebase authentication, account generation, and exact
device matching remain authoritative. The current product does not claim
cryptographic device authentication; strengthening that boundary is a separate
security decision.

User exports include frame-request metadata and explicit conversation-photo
manifests. When the dedicated object is readable, the manifest carries
`bytes_base64`; if it is unavailable, `bytes_available: false` makes that
limitation explicit rather than silently omitting the image.
