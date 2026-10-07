# Episode writer deadline audit

Source audit at Round 10; no live infrastructure/configuration reads. Deployment
values can impose tighter limits than these code defaults. No outer limit is
changed here. Proposed C7=120s/C6=180s is distinct from the shared 60s structure
constant used by baseline, legacy and auxiliary notes paths.

| Boundary | Existing limit / behavior | Episode consequence |
| --- | --- | --- |
| Notes SDK (`model_config.py`, `clients.py`) | Foreground default 60s; explicit timeout overrides SDK; episode disables transport retries | Episode tiers pass their own budget |
| Generated gateway `conv_structure` route (`config_loader.py`, `generated_route_overrides.yaml`) | Streaming-capable route defaults 120s total provider deadline; no per-request timeout override | C6 proposal 180s blocked: effective 115s; no shared-route increase |
| Gateway model options | Existing `conv_structure` gateway override is `reasoning_effort: low`; direct production model config has none | C7 adds no request override; direct OpenRouter default-effort evaluation is not proof of gateway effort parity |
| HTTP middleware (`main.py`, `utils/other/timeout.py`) | Default 120s whole request; finalization worker path 1500s | Extended budgets restricted to already-leased durable finalizer; synchronous create/reprocess stay C7/60s |
| Cloud Tasks (`utils/cloud_tasks.py`) | Dispatch deadline 1500s; named generation tasks dedupe; attempts capped (default 5); Redis run lock 1800s | At most 115s C6 + 120s C7 fallback; no third writer/repair |
| Durable job (`database/conversation_finalization_jobs.py`) | Lease 1500s; epoch/generation fences; completed replay skips processing; fanout claim precedes side effects | No new job/read/transaction; existing retry/idempotency ownership stays |
| Inline admission (`lifecycle.py`) | Orphan threshold 900s; heartbeat interval 225s at default | Synchronous budget unchanged; no orphan timeout increased |
| Pusher (`routers/pusher.py`, `pusher_finalization.py`) | No processing `wait_for`; disconnect drain 30s; cleanup cancels; process shutdown drain 10s; pod grace 120s; WS LB 3600s | Shutdown can interrupt a leased job; existing reconciliation/retry/fences recover it. These limits do not guarantee uninterrupted C6 completion |
| Listen (`routers/listen/conversations.py`, `runtime.py`) | Schedules durable finalization rather than running notes inside WS; connection drain is separate | No extended notes inside listen drain |
| App / desktop | Mobile HTTP pool defaults 30s/attempt, desktop shared transport defaults 30s; create/reprocess do not override it; capture completion is persisted and refreshed asynchronously | A UI wait is not a writer/job deadline; no client waits changed |

Cached 24-DEV distribution: C7 median 17.15s, p90 45.76s, max 53.23s;
C6 median 37.23s, p90 121.81s, p95 134.95s, max 163.94s. A 120s C7 budget
covers measured tails with headroom. An independent 180s C6 budget would cover
this sample, but requires a separately accepted episode gateway lane and serving
completion/drain audit. Do not silently raise the shared route or baseline budget.
Keep rollout at zero until effective-deadline/fallback results and gateway effort
parity are accepted. Provider read timeouts are not strict wall-clock cancellation;
process termination and requests abandoned by clients remain inherited risks.

Direct DEV requests using a 115s socket deadline returned complete notes as late
as 136.40s (deterministic tiered) / 151.54s including selector (Jev tiered), with
zero endpoint timeout/fallback errors. These are quiet-read timeouts, NOT total
wall-clock deadlines; they do not establish success behind the 120s gateway.
Receipts mark `writer_deadline_overrun` and disable paid repair while preserving
an already completed usable note. Fakes pin a real timeout buying exactly one C7
rewrite. Gateway timeout/cancellation and blended fallback billing still need
serving acceptance; no live gateway or production job was called in this round.
