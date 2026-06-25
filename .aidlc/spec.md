# Auto-router v2 — Make it production-useful

## Objective

v1 delivered a framework (scoring, registries, daily refresh, endpoint, desktop client, demo, tests). v2 makes the auto-router actually **used** and **measurable** in production:

1. **Authentication** — the v1 endpoint is unauthenticated (cubic P2 #17). Upstream's `/v1/auto/model-pick` requires auth (`Depends(get_current_user_uid)`). v2 matches that pattern.
2. **Observability metrics endpoint** — `/v1/auto-router/metrics` exposes pick history (last N picks, counts per model, score distribution, cache age). Without this, we can't measure if the router is improving things.
3. **Wire one Omi path** — `ChatProvider` consults `AutoRouter` for chat model selection when "Auto" mode is active. Demonstrates end-to-end value: a real Omi feature path uses the router to pick a model.

This is still a **foundation / MVP** — not a full production rollout. The goal is one wired path + the metrics to measure it, not all 5 paths wired.

## Upstream context (unchanged from v1)

v2 still does NOT modify:
- `backend/routers/auto_model.py` (upstream's narrow realtime-voice picker)
- `desktop/macos/Desktop/Sources/RealtimeOmni/AutoModelSelector.swift` (upstream's desktop client)
- `ChatProvider.swift` (we add a NEW helper function alongside; we don't replace existing behavior)

v2 only EXTENDS the auto-router we built in v1. It does not touch upstream code.

## What's new in v2

| Area | v1 (already done) | v2 (this cycle) |
|---|---|---|
| Endpoint | `GET /v1/auto-router/pick?task=...` (UNAUTHENTICATED) | Same endpoint, now requires auth via `Depends(get_current_user_uid)` |
| Observability | None | New `GET /v1/auto-router/metrics` endpoint |
| Desktop client | `AutoRouter` singleton with per-task UserDefaults cache | (unchanged — desktop already has its own auth via AuthService) |
| Wiring | None — endpoint exists but no Omi code calls it | `ChatProvider` consults `AutoRouter` for the "Auto" model pick when `selectedModel` is empty/"Auto" |
| Tests | 142 backend + 15 desktop = 157 | +metrics endpoint tests, +auth tests, +wiring tests |

## Detailed design

### 1. Authentication

The v1 endpoint accepts any `?task=...` request. v2 requires the same `uid` parameter that upstream uses:

```python
@router.get("/v1/auto-router/pick")
async def auto_router_pick(
    task: str = Query(..., description="Task name to pick a model for"),
    uid: str = Depends(get_current_user_uid),  # NEW
):
    ...
```

The `uid` is currently unused (the response doesn't depend on the user) but matching upstream's pattern sets us up for per-user preferences in v3. Tests that call the endpoint need to pass `uid="test-uid"` or use FastAPI's `app.dependency_overrides`.

### 2. Observability metrics endpoint

`GET /v1/auto-router/metrics` returns:

```json
{
  "generated_at": "2026-06-25T13:00:00Z",
  "cache": {
    "last_loaded_at": "2026-06-25T10:00:00Z",
    "age_seconds": 10800,
    "is_fresh": true
  },
  "tasks": {
    "ptt_response": {
      "weights": {"quality": 0.4, "latency": 0.5, "cost": 0.1},
      "candidate_count": 4,
      "current_pick": "gemini-1-5-flash-8b-exp",
      "current_score": 0.865
    },
    ...
  },
  "pick_history": [
    {
      "timestamp": "2026-06-25T12:59:42Z",
      "task": "ptt_response",
      "model": "gemini-1-5-flash-8b-exp",
      "score": 0.865,
      "weights_used": {"quality": 0.4, "latency": 0.5, "cost": 0.1}
    },
    ...up to 100 most recent picks
  ]
}
```

`pick_history` is an in-memory ring buffer (capped at 100 entries). It records every successful pick made by the endpoint. This is **process-local** — for production observability, the user would integrate with a metrics system (Prometheus, etc.) which is out of scope for v2.

**Why this matters:** Without metrics, we can't answer "is the router actually picking the best model?" or "how often does the pick change day-to-day?" v2 adds the bare minimum to answer those questions.

### 3. ChatProvider wiring

The current `ChatProvider.swift` line 988-990 picks the model like this:

```swift
let floatingModel = ShortcutSettings.shared.selectedModel.isEmpty
    ? ModelQoS.Claude.defaultSelection
    : ShortcutSettings.shared.selectedModel
```

For `general_assistant` (chat), this either:
- Returns a hardcoded default (`ModelQoS.Claude.defaultSelection`), or
- Returns whatever the user picked in settings

v2 adds: if the user's setting is empty/blank/equals "Auto" (case-insensitive), consult `AutoRouter.shared.pick(.generalAssistant)` instead. Falls back to the current behavior if the router returns nil.

```swift
let floatingModel: String
let settingsModel = ShortcutSettings.shared.selectedModel
if settingsModel.isEmpty || settingsModel.lowercased() == "auto" {
    // Consult the auto-router for chat model selection.
    if let routerPick = AutoRouter.shared.currentPick(for: .generalAssistant) {
        floatingModel = routerPick
    } else {
        // No cached pick yet — fall back to the existing default.
        // (Don't block on the network here; AutoRouter caches in background.)
        floatingModel = ModelQoS.Claude.defaultSelection
    }
} else {
    floatingModel = settingsModel
}
```

**Why `currentPick` not `pick`:** `currentPick` is a synchronous UserDefaults read (no network). Calling `pick` would be async and would block the chat init. The desktop client prefetches picks in the background (next AIDLC task — out of scope for v2).

**What if the router is empty?** Fall back to the current default. No behavior change for users who haven't enabled Auto mode.

## Out of scope (v2)

- **Real Artificial Analysis integration** — `benchmarks.json` stays as the source. AA key handling is a v3 task.
- **Wiring into `RealtimeHubController` (PTT), screenshot understanding, transcription, embedding** — these are v3+ tasks. v2 only wires ONE path (chat) to demonstrate the pattern.
- **Per-user personalization** — `uid` is captured but unused in v2. v3 can add per-user weights.
- **Per-task pick history persistence** — in-memory only. v3 can add Redis/DB persistence.
- **Production observability integration** (Prometheus, DataDog, etc.) — v2 exposes the data; v3 integrates with actual monitoring.
- **Modifying upstream `/v1/auto/model-pick`** — still out of scope; both routers coexist.

## Acceptance criteria

### Backend (v2 additions)
1. `GET /v1/auto-router/pick?task=...` requires `uid` (verified by `Depends(get_current_user_uid)`); missing/invalid auth → 401
2. The endpoint continues to work for authenticated callers (backward compatible with v1 callers that have a uid)
3. `GET /v1/auto-router/metrics` returns the documented JSON shape
4. Every successful `pick` call records an entry in `pick_history` (capped at 100, FIFO)
5. Pick history includes timestamp, task, model, score, weights used
6. `cache.last_loaded_at` matches `DailyRefreshCache.last_loaded_wall_time()` (consistent)
7. `cache.age_seconds` matches `DailyRefreshCache.age_seconds()` (consistent)
8. Metrics endpoint is also auth-protected (matches upstream pattern)
9. Test counts: +6 endpoint tests (auth, metrics, pick history); +2 new tests
10. `bash backend/test.sh` passes (the new tests are wired into the script)

### Desktop (v2 addition)
11. `ChatProvider` consults `AutoRouter.shared.currentPick(for: .generalAssistant)` when settings is empty or "Auto"
12. Falls back to `ModelQoS.Claude.defaultSelection` if router has no cached pick
13. No network call in the chat-init path (currentPick is sync UserDefaults)
14. New Swift test verifies the routing logic (empty settings → router pick; "Auto" → router pick; "claude-sonnet-4-6" → user's choice)

### Cross-cutting
15. v1 tests still pass (no regressions)
16. Black --check clean
17. `git diff upstream/main -- backend/routers/auto_model.py desktop/macos/Desktop/Sources/RealtimeOmni/AutoModelSelector.swift` is empty (we don't touch upstream)
18. PR diff is ≤500 lines (smaller than v1 because we're extending not building from scratch)

## Open questions

1. **Pick history retention**: ring buffer at 100 entries in-memory, or persistent (Redis)? **Recommendation: in-memory for v2; persistent for v3.** Persistent adds operational complexity (Redis dependency for the auto-router) that v1 explicitly avoided.

2. **Authentication for the metrics endpoint**: should it be the same as the pick endpoint? **Recommendation: yes — same `Depends(get_current_user_uid)`.** Metrics expose per-user data in the future; auth now sets the pattern.

3. **Where to record the pick**: in the endpoint after the scoring loop, or in a separate observer? **Recommendation: in the endpoint directly** (simpler; metrics are a side effect of the pick). A separate observer would add an import / abstraction that v2 doesn't need.

4. **ChatProvider wiring: do we break the current `selectedModel` semantics?** **Recommendation: NO.** We only change behavior when `selectedModel` is empty OR equals "auto" (case-insensitive). Users with a specific model selected continue to get that model.

5. **Should `currentPick` block on first call to trigger a refresh?** **Recommendation: NO.** The first call returns nil (cache empty); ChatProvider falls back to the default. The user gets the chat working immediately, and the next time they make a request, the router will have populated the cache. This matches the pattern of "default behavior is good enough; the router optimizes when it can."
