# Frame-request pixel retention

`BUCKET_FRAME_REQUESTS` is a dedicated runtime binding. It must point at a
bucket whose lifecycle policy does not expire objects: conversation-attached
objects are permanent for the lifetime of their conversation. Temporary
requested/claimed/uploaded objects are removed by the scheduled retention
worker after their Firestore row reaches a terminal cleanup state.

The worker retries external deletion independently of queue delivery and the
rollout kill switch. Account deletion and conversation deletion enumerate all
queue pages and photo subcollections before deleting opaque objects; an
attached object is never selected by temporary cleanup.

Deployment evidence must include the bucket name, the absence of an object
expiration lifecycle rule, and the runtime env binding. This source tree does
not mutate GCP; the deploy receipt is an integration gate.

Run the offline predeploy check with `python backend/scripts/validate_frame_request_bucket_contract.py
--bucket <dedicated-bucket> --lifecycle-json <describe-output.json>`. The
desktop `device_id` is an owner-scoped routing and recovery identifier, not a
standalone credential: Firebase authentication, account generation, and exact
device matching remain authoritative. The current product does not claim
cryptographic device authentication; strengthening that boundary is a separate
security decision.

User exports include frame-request metadata and explicit conversation-photo
manifests. When the dedicated object is readable, the manifest carries
`bytes_base64`; if it is unavailable, `bytes_available: false` makes that
limitation explicit rather than silently omitting the image.
