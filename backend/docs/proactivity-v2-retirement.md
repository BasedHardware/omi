# Legacy desktop proactivity retirement

The 2026-10-03 integration retires the screen Advice/Insight timer, context buckets and director, JIT proactivity trigger matching/triage/delivery, and the parked Interject reply surface. Focus remains on both desktops; only its JIT suppression is removed.

## Released clients

`POST /v1/desktop/proactivity/completions` returns a static `429`, `Retry-After: 3600`, zero quota headers, and `detail.error = feature_retired`. The handler has no request model or authentication dependencies and does no subscription, Redis, PostHog, or provider work. This uses released clients' existing bounded cooldown instead of repeatedly producing unknown 404 errors.

`POST /v1/jit/proactivity/reservations` and `POST /v1/jit/trigger-feedback` return static `410` retirement responses. Deprecated request and successful-response shapes remain OpenAPI metadata only; they do not run validation or authentication. `GET /v1/jit/trigger-snapshot` retains owner authentication and returns the existing disabled, incomplete, empty envelope without a database scan or rollout lookup. Explicit legacy JIT budget headers at desktop chat and the gateway are rejected before provider dispatch.

Already-released Insight and Focus clients using `/v1/proxy/gemini` remain supported. Models and prompt text are not producer identities. The shared `desktop_proactivity` Gemini accounting feature and lane attribution remain in place for retained assistants.

## Retained boundaries

- `/v1/jit/rollout-decision` and `utils/jit_rollout.py` retain their behavior and authority for canonical memory, knowledge tools, first-open processing, and frame tools.
- Canonical mirror storage and APIs remain; desktop mirror synchronization no longer depends on a trigger snapshot or notification producer.
- Conversation mentor, `screen_task_jev_gate` task extraction, memory extraction, live notes, goals, home suggestions, dictation, embeddings/Rewind, daily recap and interesting-memory review remain.
- Floating-bar/notch rendering and Windows shared toast delivery remain available for v2.
- Legacy export/account-wipe collection names remain so historical data remains exportable and erasable. No production account cleanup is part of this cut.

## Local database upgrades

Historical GRDB migration registrations remain append-only. A forward migration detaches `subject_bindings` from the removed bucket foreign key while preserving binding values, then drops context bucket/director/delivery tables and JIT proactivity runtime tables. Canonical mirrors, staged mirror pages, memory, task extraction, Focus, Rewind, live notes and goals remain.

Windows migration 3 drops only the trigger, wakeup, reservation, ambient-state, feedback and installation-identity tables. Canonical fact/history/playbook/alias mirrors, mirror receipts and keyframe cleanup authority remain. Tests use synthetic local databases; no real user database is opened.

## Deferred cleanup

Renaming the shared JIT rollout authority is a separate change. Full JIT QA harness/runbook retirement is also deferred: pure QA budget/header/receipt helpers and historical fixture vocabulary may remain, but they no longer admit live proactivity inference. The emulator fixture for a lost historical reservation remains as a memory-sweep repair safety test.

The knowledge-base project record and cost/defect evidence are coordinator-owned and are not edited by this integration lane. Update their live architecture links after the final integrated PR is reviewed.

## Desktop feed presentation seam

The Mac `ProactivityNotificationAdapter` and Windows `presentProactivityNotification` accept the spine's generated feed item. They preserve the existing master/frequency controls and capture the current owner/session. Unknown producers can render when the target is supported; unknown targets, handled items, and stale sessions cannot present. Conversation/task clicks navigate to the typed object; they never accept a task or open a supplied URL.

Feed consumers provide an owner-scoped durable shown-receipt lookup and an outcome callback. They own polling, push/feed deduplication, expiry, persistence and retry of receipts. Adapters emit generated outcome requests with deterministic per-owner/item/action event IDs. A queued or suppressed card emits no `shown`; explicit dismiss and timeout remain separate from open. Mac bar and native fallback share a presentation UUID; Windows routes toast interaction IPC through the main process and accepts it only from the toast window. Native callbacks are session-bound and are intentionally discarded after process/session replacement; the durable feed remains the recovery surface.

Neither adapter writes the retired context-delivery table or treats Windows' legacy shared notification history as the v2 ledger. Feed-backed Mac cards do not create duplicate chat journal entries. The feed consumer must persist a shown receipt before returning from its outcome callback and serialize concurrent push/feed presentation attempts for the same item.
