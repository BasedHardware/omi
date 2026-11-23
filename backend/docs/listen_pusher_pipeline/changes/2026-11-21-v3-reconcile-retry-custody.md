# 2026-11-21: confirm the successor before acknowledging a v3 builder race

A Cloud Tasks name can still be reserved after its task finishes. A live v3
builder race now acknowledges its retry only after Cloud Tasks confirms a
new or undispatched future owner wake. An owner task that finds the builder
lease busy uses the same check. On an ambiguous create or lookup, the task
route returns 503 so the current delivery remains retryable.

The wake carries only the owner and starts a fresh reconcile under the builder
lease. This reloads any committed prefix and preserves the existing pending
markers and their age. The wake cannot claim a summary write. Projection
and notes transaction fences still determine what can commit or settle.

The patch adds no flag or queue setting. Conflicting names use a bounded BASIC
task lookup. If the invoker lacks lookup access, the current delivery keeps
retry custody. Rollback is a reviewed revert. The focused tests cover retained
names, active and future wakes, lease loss and replay of a committed prefix.

[Recording-derived conversations v3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
