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

## Desktop proactivity retirement

The ambient/planned trigger runtime, watchlists, nano triage and delivery were
removed on 2026-10-03. Trigger snapshots now return the explicit disabled,
incomplete empty shape without scanning storage; reservations and trigger
feedback return static 410 responses. See [the retirement contract](proactivity-v2-retirement.md).

The first-open behavior above, `/v1/jit/rollout-decision`, and canonical-memory
mirror APIs remain unchanged. Desktop mirror synchronization has its own
startup/chat or capture-coordinator entry points and does not require a
proactivity notification or trigger snapshot.
