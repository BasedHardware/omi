# JIT first-open runtime

Conversation capture remains legacy full-eager unless the authenticated backend
rollout authority returns a known enabled decision and the persisted source is
supported. Clients cannot supply a cohort or enrollment flag.

When enabled, summary creation and retrieval indexing remain on capture. The
backend transactionally writes `jit_first_open.state=pending` before deferring
folder assignment and conversation-app fan-out (automatic goal updates are
removed from the JIT featureset entirely; goals change only through manual or
explicit actions). A detail read claims a token-fenced lease and dispatches
those effects. Concurrent/repeated opens do not duplicate a live claim;
failures return to pending and expired leases can be reclaimed. Completion is
accepted only from the current token. Outstanding work re-reads uncached
paid-boundary rollout/kill authority before each provider call and again
before every result, usage, folder, or receipt commit. A kill that changes while a provider request is already in
flight cannot retract that paid request, but its result is suspended and no
mutation commits. Kill/off/unknown never drain persisted work.

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
The backend reads the trusted ledger head again after exhausting the query; a
generation/head/sequence change makes the receipt incomplete. The revision
hash binds canonical row order, identity, condition, action, and wakeup budget,
so content changes cannot reuse a prior complete receipt.

macOS transactionally replaces its local mirror from a complete snapshot, so
an empty snapshot deletes every mirrored trigger and stale/conflicting receipts
cannot win. Planned triggers are evaluated locally from bounded current facts
and metadata. A deterministic winner acquires a token-fenced wakeup lease before
exactly one text-only full agent turn; presentation success or failure settles
the durable receipt and expired claims can be retried. The turn performs no
continuous vision pass and no historical keyword recall. It submits the
immutable owner authorization to every agent-runtime boundary in `ask` mode;
the kernel hard-denies non-read-only tools on the JIT service surface.

Only after a complete snapshot proves there is no planned match or ambiguous
planned selector may the ambient lane proceed. Material change is a durable
comparison of normalized validated facts for the stable bucket identity; fact
order, screenshot ID, capture time, and revisit-only version churn do not spend
another nano attempt. Existing context-bucket notify-worthiness, validated evidence, delivery budget,
workstream context, and CandidateSink remain its authorities. A model-free gate
runs first, followed by at most one nano triage; nano attempts have a durable
eight-per-day cap, including malformed/failing attempts. Approval may purchase
one text-only full turn through the same delivery ledger and a one-per-context
ambient wakeup claim. Planned and ambient claims share the observation
continuity key, so they cannot both deliver for the same evidence. Neither gate
matches historical-intent words, creates a passive permanent trigger, or starts
a continuous model/vision loop. Ambient `task_candidate` output must cite the
validated actionable facts that CandidateSink graduates before presentation;
planned output accepts only insight or silence.
