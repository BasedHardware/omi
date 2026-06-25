# Plan: Auto-router v2 — Make it production-useful

## Dependency Graph

```
T-201: Auth on pick endpoint
   │
   ├──> T-202: Metrics endpoint + pick history
   │         │
   │         └──> T-204: Demo updates (show metrics + auth)
   │
   └──> T-203: Wire ChatProvider to consult AutoRouter
              │
              └──> T-205: Doc updates
```

T-201 is the foundation (everything auth-protected uses the same dependency).
T-202 and T-203 are independent after T-201. T-204 depends on T-202 (needs the metrics endpoint to demo). T-205 is last (consolidates the cycle).

## Sizing summary

| Task | Effort | Files | Cumulative |
|---|---|---|---|
| T-201 | S | 2 modified | 2 |
| T-202 | M | 4 new + 2 modified | 8 |
| T-203 | S | 2 modified | 10 |
| T-204 | S | 1 modified | 11 |
| T-205 | S | 2 modified | 13 |

Total: ~13 files, ~400 lines code + ~300 lines tests = ~700 lines. Within the v2 spec's ≤500-line PR diff target.

---

## Tasks

### T-201: Auth on pick endpoint

**Files:**
- `backend/routers/auto_router.py` (modify — add `Depends` import + `uid` param)
- `backend/tests/unit/test_auto_router_endpoint.py` (modify — add `uid` to all calls + new auth tests)

**Description:**
Add `Depends(get_current_user_uid)` to the existing pick endpoint. The `uid` is captured but not yet used in v2 (per-user prefs is v3). This:
- Matches upstream's `/v1/auto/model-pick` pattern
- Sets up the codebase for v3's per-user weight overrides
- Closes cubic P2 #17 ("unauthenticated model-pick endpoint")

**Acceptance criteria:**
- [ ] `GET /v1/auto-router/pick?task=...` requires authentication; missing/invalid auth returns 401
- [ ] The endpoint's FastAPI signature includes `uid: str = Depends(get_current_user_uid)`
- [ ] Existing endpoint tests updated to pass `uid="test-uid"` (or use `app.dependency_overrides` for the override)
- [ ] New test: missing/invalid auth → 401
- [ ] New test: valid auth → 200 (response shape unchanged)

**Test approach:**
- Existing TestClient-based tests need updating (add `uid` to all request helpers)
- New test class `TestAuth` with cases for missing header, malformed header, valid header

**Estimated effort:** S (15-30 min, ~30 lines + ~50 lines tests)

---

### T-202: Metrics endpoint + pick history

**Files:**
- `backend/routers/auto_router.py` (modify — add `/v1/auto-router/metrics` endpoint + record each pick)
- `backend/utils/auto_router/metrics.py` (new — `PickHistory` ring buffer + `MetricsCollector`)
- `backend/tests/unit/test_auto_router_metrics.py` (new — metrics endpoint tests + ring buffer tests)

**Description:**
Add a new `/v1/auto-router/metrics` endpoint that exposes:
- Cache state (`last_loaded_at`, `age_seconds`, `is_fresh`)
- Per-task current state (weights, candidate count, current pick, current score)
- `pick_history`: in-memory ring buffer (last 100 picks, FIFO)

**Architecture:**
- `PickHistory` class — thread-safe ring buffer (capped at 100). Methods: `record(task, model, score, weights)`, `snapshot()` returns list.
- `MetricsCollector` singleton — owns the `PickHistory` and provides `record_pick(...)` + `current_state(task_registry, model_registry)`.
- The pick endpoint records each successful pick to `MetricsCollector` BEFORE returning the response.
- The metrics endpoint reads from `MetricsCollector` and assembles the response.

**Acceptance criteria:**
- [ ] `GET /v1/auto-router/metrics` returns the documented JSON shape (cache + tasks + pick_history)
- [ ] Every successful `pick` call records an entry in `pick_history` (capped at 100, FIFO)
- [ ] Pick history includes timestamp, task, model, score, weights used
- [ ] Metrics endpoint is also auth-protected (matches T-201's `Depends`)
- [ ] `cache.last_loaded_at` matches `DailyRefreshCache.last_loaded_wall_time()`
- [ ] `cache.age_seconds` matches `DailyRefreshCache.age_seconds()`
- [ ] Per-task `current_pick` is the top-scoring model (the same one `/pick` returns)
- [ ] Ring buffer is thread-safe (concurrent `record` calls don't corrupt it)
- [ ] Pick history is empty after process restart (in-memory only — documented)

**Test approach:**
- `PickHistory`: test FIFO eviction (101st record drops the oldest), test thread-safety with `threading.Barrier` + 100 concurrent records
- `MetricsCollector`: test `current_state` returns the right shape
- Endpoint tests: test the response shape, test that 2 calls to `/pick` produce 2 entries in history

**Estimated effort:** M (1-2 hours, ~150 lines source + ~150 lines tests)

---

### T-203: Wire ChatProvider to consult AutoRouter

**Files:**
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift` (modify — add the routing helper)
- `desktop/macos/Desktop/Tests/AutoRouterWiringTests.swift` (new — verify the routing logic)

**Description:**
Add a small helper that decides which model to use for the chat path:
- If `ShortcutSettings.shared.selectedModel` is empty OR equals "Auto" (case-insensitive):
  - Try `AutoRouter.shared.currentPick(for: .generalAssistant)` (sync UserDefaults read)
  - If non-nil, use it
  - If nil, fall back to `ModelQoS.Claude.defaultSelection` (current behavior)
- Otherwise, use the user's setting (current behavior — unchanged)

**Why `currentPick` not `pick`:** `currentPick` is a synchronous UserDefaults read. `pick` is async (network call). Blocking the chat init on a network call is bad UX. The router's daily refresh prefetches picks in the background; the desktop client already calls `refreshIfStale(for: .generalAssistant)` somewhere (TBD where to add if not present).

**Where to put the helper:**
- New file: `desktop/macos/Desktop/Sources/Providers/ChatModelRouter.swift` — encapsulates the decision logic, testable in isolation
- Wire in `ChatProvider` by replacing the line 988-990 model selection with a call to the helper

**Acceptance criteria:**
- [ ] `ChatModelRouter.shared.modelForChat()` returns the router pick when settings is empty
- [ ] `ChatModelRouter.shared.modelForChat()` returns the router pick when settings is "Auto" (case-insensitive)
- [ ] `ChatModelRouter.shared.modelForChat()` returns the user's setting when it's a specific model
- [ ] `ChatModelRouter.shared.modelForChat()` falls back to `ModelQoS.Claude.defaultSelection` if router has no cached pick
- [ ] `ChatProvider` uses the helper for chat model selection (replaces line 988-990)
- [ ] No new behavior for users with a specific model selected (regression-safe)
- [ ] New Swift test covers all 4 cases above (using dependency injection of the router + settings)

**Test approach:**
- XCTest with `URLProtocol` mock for the auto-router endpoint (to populate the cache in tests)
- Or: use `AutoRouter.shared.store(_:for:)` directly to seed the cache (simpler, no HTTP mocking)
- Test class: `AutoRouterWiringTests` with 4 test methods (one per case)

**Estimated effort:** S (1-1.5 hours, ~80 lines Swift + ~150 lines Swift tests)

---

### T-204: Demo updates

**Files:**
- `backend/utils/auto_router/demo/run.py` (modify — add a metrics demo + auth requirement note)

**Description:**
The current demo runs scoring on local data without going through the endpoint. v2 adds:
- A new demo section that calls `/v1/auto-router/pick` (showing the actual endpoint) and then `/v1/auto-router/metrics` (showing what got recorded)
- A note in the existing demos that the endpoint now requires auth (use a test uid in the demo)
- This requires the demo to spin up a TestClient (no real uvicorn)

**Acceptance criteria:**
- [ ] Demo runs without error and produces output for the new section
- [ ] New section: `Demo 4: Hit the live endpoint and check metrics`
- [ ] New section calls `/v1/auto-router/pick?task=ptt_response` and prints the response
- [ ] New section calls `/v1/auto-router/metrics` and prints the recorded pick
- [ ] The test_auto_router_demo.py test suite still passes (it asserts on Demo 1, 2, 3 picks — Demo 4 should be appended after)

**Test approach:**
- Update `test_auto_router_demo.py` to handle the new section (just count sections, don't assert on Demo 4's specific output since it depends on the cache state)
- Verify the demo script's `if __name__ == "__main__":` block runs without error

**Estimated effort:** S (30-45 min, ~30 lines added to demo + ~10 lines test updates)

---

### T-205: Doc updates

**Files:**
- `docs/doc/developer/auto-router.mdx` (modify — add v2 section: authentication, metrics, wiring)
- `docs/auto-router-demo.md` (modify — add Demo 4 walkthrough)
- `backend/utils/auto_router/README.md` (modify — mention auth requirement)

**Description:**
v2 documentation updates:
- `auto-router.mdx` (developer guide): add a "v2 (production-useful)" section with auth, metrics endpoint, and wiring details. Update the architecture diagram.
- `auto-router-demo.md`: add Demo 4 walkthrough (similar to how Demos 1-3 are documented).
- `backend/utils/auto_router/README.md`: update "Quick start" to show auth header (or test uid), update the endpoint response shape to reflect the new structure.

**Acceptance criteria:**
- [ ] `auto-router.mdx` has a new section explaining v2 (auth, metrics, wiring)
- [ ] `auto-router-demo.md` has Demo 4 walkthrough
- [ ] `README.md` mentions auth in the Quick start
- [ ] All cross-references in the docs are valid (no broken links)
- [ ] Demo expected-pick tests still pass (no false positives from the new section)

**Test approach:**
- Manual visual inspection
- `PYENV_VERSION=3.12.8 black --check docs/ backend/utils/auto_router/README.md` (docs don't get black'd but verify nothing's broken)
- Re-run `test_auto_router_demo.py` to confirm Demo 4 doesn't break Demo 1-3

**Estimated effort:** S (30-45 min, ~80 lines doc updates)

---

## Implementation Notes

- **Commit strategy**: 1 commit per task (T-201 through T-205) + 1 commit for spec/plan/state + 1 commit for review. Per repo `AGENTS.md` "individual commits per file, not bulk commits" is satisfied within each task (source + tests paired).
- **No push, no PR** until user explicit approval per repo `AGENTS.md`.
- **Branch**: `feat/auto-router-v2` (already created from `feat/auto-router-v1`).
- **Python version**: 3.12 for local checks (matches CI's black 26.5.1). 3.11 is what backend declares; tests pass under both.
- **Auth pattern**: `from utils.other.endpoints import get_current_user_uid` — already used by upstream's `/v1/auto/model-pick`.
- **Pick history thread safety**: `collections.deque(maxlen=100)` with a `threading.Lock` for the `record` and `snapshot` operations. Simple, correct, no external deps.
- **Metrics endpoint security**: same auth as pick. Per cubic P2 #17, exposing picks publicly is a leak. Auth now sets the pattern for v3 per-user metrics.
- **ChatProvider regression safety**: we only change behavior when `selectedModel` is empty or "Auto". Users with specific model selections see zero behavior change.
- **Demo test runner**: `tests/unit/test_auto_router_demo.py` runs the demo as a subprocess. With v2's new section, the assertions on Demos 1-3 should still hold; Demo 4 is appended.

## Sizing Summary

| Task | Effort | Files | Status |
|---|---|---|---|
| T-201 | S | 2 | Pending |
| T-202 | M | 6 (4 new + 2 modified) | Pending |
| T-203 | S | 2 | Pending |
| T-204 | S | 1 | Pending |
| T-205 | S | 3 | Pending |
| **Total** | | **~13** | |

PR diff target: ≤500 lines. ~400 code + ~300 tests + ~80 doc = ~780 lines; doc lines are not counted in diff budget.
