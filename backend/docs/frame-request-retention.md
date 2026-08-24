# Frame-request pixel retention

`BUCKET_FRAME_REQUESTS` is a dedicated runtime binding. It must point at a
bucket whose lifecycle policy does not expire objects: conversation-attached
objects are permanent for the lifetime of their conversation. Temporary
requested/claimed/uploaded objects are removed by the scheduled retention
worker after their Firestore row reaches a terminal cleanup state.

The worker retries external deletion independently of queue delivery and the
rollout kill switch. Account deletion and conversation deletion enumerate all
queue pages before deleting opaque objects; an attached object is never
selected by temporary cleanup.

Deployment evidence must include the bucket name, the absence of an object
expiration lifecycle rule, and the runtime env binding. This source tree does
not mutate GCP; the deploy receipt is an integration gate.
