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

The context-entered runtime first reads authenticated `GET
/v1/jit/rollout-decision`; off, unknown, and kill-switch states preserve the
legacy context-bucket evaluator. An admitted owner then reads `GET
/v1/jit/trigger-snapshot`. This endpoint is read-only, non-cacheable, and emits
an exhaustive owner/account-generation/head/sequence/revision receipt. An
active trigger is usable only when it is primary-user, intent-backed, open, and
carries a bounded `agent_prompt` action. Any malformed row, mixed generation,
query failure, or size overflow marks the whole snapshot incomplete.

macOS transactionally replaces its local mirror from a complete snapshot, so
an empty snapshot deletes every mirrored trigger and stale/conflicting receipts
cannot win. Planned triggers are evaluated locally from bounded current facts
and metadata. A deterministic winner acquires a token-fenced wakeup lease before
exactly one text-only full agent turn; presentation success or failure settles
the durable receipt and expired claims can be retried. The turn performs no
continuous vision pass and no historical keyword recall.

Only after a complete snapshot proves there is no planned match or ambiguous
planned selector may the ambient lane proceed. Existing context-bucket material
change, version novelty, notify-worthiness, validated evidence, delivery budget,
workstream context, and CandidateSink remain its authorities. A model-free gate
runs first, followed by at most one nano triage; nano attempts have a durable
eight-per-day cap, including malformed/failing attempts. Approval may purchase
one text-only full turn through the same delivery ledger and a one-per-context
ambient wakeup claim. Planned and ambient claims share the observation
continuity key, so they cannot both deliver for the same evidence. Neither gate
matches historical-intent words, creates a passive permanent trigger, or starts
a continuous model/vision loop.
