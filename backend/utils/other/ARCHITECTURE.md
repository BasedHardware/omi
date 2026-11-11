# `utils/other` architecture map

This package is a grab bag by name and history, not by design. Nothing new
should land here because it "fits nowhere else"; new modules belong beside the
feature that owns them. The map below exists so the package stops growing
unread. It is required by the architecture guardrail once a package passes 12
source files.

## What is here, by concern

| Concern | Module | Owns |
| --- | --- | --- |
| Auth and account lifecycle at the HTTP/WS boundary | `endpoints.py` | `get_current_user_uid`, token verification, account-deletion and cutover gates that every router depends on. This is the package's only load-bearing import for request handling. |
| Object storage | `storage.py` | GCS bucket access, public URL derivation, owner-scoped write gate, per-user deletion sweep, audio decode helpers. |
| Local dev storage adapter | `local_storage.py` | Filesystem stand-in for `storage.py` used only by the owned local dev harness; never selected in a deployed image. |
| Chat file attachments | `chat_file.py` | Provider upload/expiry of files attached to chat turns, and the typed errors the chat route maps to user-facing failures. |
| Daily summary job | `notifications.py` | The scheduled daily-summary job: per-user fan-out, isolation, budgets, checkpoint cursor, FCM send, `day_summary` webhook. |
| Daily summary bounds | `daily_summary_budget.py` | Bounds the job uses: bounded conversation selection for the generator input (pure) and the resume checkpoint. The cursor helpers do synchronous Redis I/O and must be called through `run_blocking(db_executor, ...)`; every one of them is fail-soft, so losing the checkpoint costs a re-walk and never a summary. |
| Bounded list reads | `list_budget.py` | Request-scoped time and document budget for list GET reads (`FC-bounded-read-exceeds-request-budget`). |
| Request timeout | `timeout.py` | `TimeoutMiddleware`, the per-request wall-clock budget. |
| Background execution primitives | `task.py`, `jobs.py`, `deferred_delete.py`, `backoff.py` | `safe_create_task`, job start helper, single-thread deferred deletion, jittered backoff. Small and dependency-free. |
| Hume emotion API client | `hume.py` | Typed response models and the client for Hume batch jobs. |

## Rules that hold across the package

- `endpoints.py`, `storage.py`, and the job in `notifications.py` are imported
  at module scope by many routers; keep them import-pure (no persistence
  client at import time, see `backend-import-purity`).
- The daily-summary job is the only scheduled entry point here. Its bounds live
  in `daily_summary_budget.py` so they can be unit-tested without the job's
  Firestore and FCM surface. Fail-open paths report through
  `utils.observability.fallback.record_fallback` with component
  `daily_summary`.
- Anything that grows a new concern should move out rather than add a row
  here. Candidates already identified: `hume.py` (integration client),
  `chat_file.py` (chat feature), and the storage pair (a `storage/` package).
