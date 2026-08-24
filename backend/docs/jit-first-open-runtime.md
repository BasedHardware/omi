# JIT first-open runtime

Conversation capture remains legacy full-eager unless the authenticated backend
rollout authority returns a known enabled decision and the persisted source is
supported. Clients cannot supply a cohort or enrollment flag.

When enabled, summary creation and retrieval indexing remain on capture. The
backend transactionally writes `jit_first_open.state=pending` before deferring
folder assignment, goal progress, and conversation-app fan-out. A detail read
claims a token-fenced lease and dispatches those effects. Concurrent/repeated
opens do not duplicate a live claim; failures return to pending and expired
leases can be reclaimed. Completion is accepted only from the current token.

If rollout authority, source classification, or durable initialization is
unknown or unavailable, capture runs the existing eager pipeline. The legacy
desktop deferred path is unchanged and remains the compatibility fallback.
