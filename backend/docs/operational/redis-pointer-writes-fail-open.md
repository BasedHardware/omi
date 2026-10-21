# Redis capacity must not tear down live listen sessions

Incident window: 2026-09-09/10, prod Redis Cloud at maxmemory (continuation of
the 2026-09-09 incident that motivated #13401).

## Signatures (GCP prod-log sensor, backend-listen)

```
ERROR:utils.async_tasks:BG task ws:<uid>:lifecycle crashed: OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")   ×~9k/14d
ERROR:utils.async_tasks:Unhandled exception in WebSocket task ws:<uid>:lifecycle [listen]: OutOfMemoryError(...)                      ×~9k/14d
Traceback ... uvicorn ... websockets_impl ... / ERROR: Exception in ASGI application                                                          ×~5.8k/14d
```

Peak observed: 1043 lifecycle-crash events in a single hour
(2026-09-10 05:00–06:00 UTC). Every event is a user's live recording session
torn down mid-recording.

## Root cause

The listen session's conversation lifecycle writes two best-effort Redis
pointers AFTER the authoritative Firestore create of the in-progress
conversation:

- `database.redis_db.set_in_progress_conversation_id` — written by
  `LiveConversationController.create_new_in_progress_conversation`
  (`routers/listen/conversations.py`) at every bootstrap and every 5-minute
  lifecycle rollover, and re-written on the reconnect resume branch.
- `database.redis_db.set_conversation_meeting_id` — desktop meeting
  attribution pointer, written in the same flow.

Under Redis maxmemory, the plain `r.set()` + `r.expire()` raised
`OutOfMemoryError` out of:

1. `lifecycle_loop` — the `lifecycle` lifetime task died;
   `utils.async_tasks.supervise_tasks` classifies ANY lifetime-task exception
   as `crash` and cancels the sibling tasks (transcript stream, heartbeat),
   killing the whole live session mid-recording.
2. `prepare()` — the same raise surfaced as `Exception in ASGI application`
   at WebSocket bootstrap.

Both writes happen AFTER the durable Firestore create. Every reader already
degrades safely when the key is absent:

- `retrieve_in_progress_conversation` → Firestore `get_in_progress_conversation`
  query;
- the meeting mapping → `_meeting_context_from_redis_mapping` returns `None`
  (already `except Exception`-guarded) and enrichment falls through to the
  calendar-overlap path.

So a capacity-full Redis must skip the write, not raise.

## Fix

Both pointer writes route through `_cache_set_fail_open` — the boundary
containment #13401 established for the geo/name caches:

- `redis.exceptions.OutOfMemoryError` (matched by class name; redis-py
  typings do not export the exception type) → skip the write, log WARNING
  `redis cache write skipped capacity_full prefix=users|conversation`, emit
  `record_fallback(component='other', from_mode='cache_write', to_mode='skip',
  reason='capacity_full', outcome='degraded')`.
- Any other Redis error still raises — only capacity failures degrade.

This is an instance of `FC-post-commit-index-maintenance-terminal`: a write
that follows the authoritative commit must not terminate the session that
already committed. Containment lives in the boundary (`redis_db`), not at call
sites; `set_in_progress_conversation_id` and `set_conversation_meeting_id`
join the geo/name cache writes as members of the same contract.

## Agent guidance

- Best-effort pointers/caches written after a durable create belong on
  `_cache_set_fail_open`, never on a bare `r.set()` — the failure class is
  open, and each new bare SET in a session-lifetime path is a new instance.
- The skip is observable two ways: the `omi_fallback_total` counter
  (`reason="capacity_full"`) and the WARNING log line on `database.redis_db`.
  Severity is deliberate: a degraded best-effort write is a WARNING, not the
  ERROR the sensor was paging on.
- Recovery is automatic: once Redis accepts writes again, the next rollover
  writes the pointer — no session restart is needed (pinned by test:
  `test_lifecycle_loop_recovers_pointer_once_capacity_restored`).

## Verification

- `tests/unit/test_redis_pointer_writes_fail_open.py` — boundary contract of
  both writers (fail-open, telemetry, non-OOM re-raise, TTLs, round-trips).
- `tests/unit/test_listen_session_survives_redis_maxmemory.py` — the real
  `LiveConversationController` driven through `lifecycle_loop`,
  `create_new_in_progress_conversation`, and `prepare()` with only the Redis
  socket faked; plus supervisor kill-mechanism documentation tests and the
  read-side fallback paths that make skipping safe.

Failure-Class: FC-post-commit-index-maintenance-terminal
