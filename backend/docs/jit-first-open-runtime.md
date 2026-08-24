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

## macOS proactivity activation boundary

The context-entered runtime reads the authenticated `GET
/v1/jit/rollout-decision` contract and treats transport, decoding, or owner
changes as unknown. It emits only bounded admission labels. The new planned and
ambient lanes remain dark even for an enabled cohort because the current
compiled trigger carries match conditions and budgets but no authoritative
action/prompt payload, and the local mirror explicitly lacks an exhaustive-sync
receipt. Until both an authoritative action source and durable wakeup/continuity
receipt exist, macOS preserves the legacy context-bucket evaluator; this keeps
ambient work from outranking an unseen planned trigger.
