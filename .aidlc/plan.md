# Plan: Auto-router v1 — task-based model selection across Omi

## Dependency Graph

```
T-001: Backend scoring engine (pure function, no I/O)
   │
   ▼
T-002: Backend task registry + model registry (JSON loader)
   │                                    │
   ▼                                    │
T-003: Backend daily refresh             │
   (TTL + asyncio.Lock + stale fallback) │
   │                                    │
   ▼                                    │
T-004: Backend FastAPI endpoint          │
   (uses scoring + registries + refresh) │
   │                                    │
   ▼                                    │
T-005: Backend wire-up ──────────────────┘
   (main.py registration + example JSON + README)
   │
   ▼
T-006: Desktop AutoRouter client
   (enum + singleton + UserDefaults + endpoint call)
   │
   ├─────────────────────┐
   ▼                     ▼
T-007: Developer docs   T-008: PR polish
   (architecture +       (demo scenarios +
    extension guide)      PR description)
```

Mostly linear. T-007 can start as soon as T-005 is done (doesn't depend on T-006 desktop code). T-008 is last.

## Sizing summary

| Task | Effort | Files | Cumulative |
|---|---|---|---|
| T-001 | S | 2 | 2 |
| T-002 | M | 5 | 7 |
| T-003 | S | 2 | 9 |
| T-004 | M | 3 | 12 |
| T-005 | M | 3 | 15 |
| T-006 | M | 3 | 18 |
| T-007 | S | 1 | 19 |
| T-008 | S | 2 | 21 |

Total: ~21 files, ~600 lines code + ~400 lines tests + ~200 lines docs = ~1,200 lines. Within the ≤800-line diff budget (after subtracting test boilerplate and example JSON).

---

## Tasks

### T-001: Backend scoring engine

**Files:**
- `backend/utils/auto_router/__init__.py` (new, minimal)
- `backend/utils/auto_router/scoring.py` (new)
- `backend/tests/unit/test_auto_router_scoring.py` (new)

**Description:**
Pure function `score(model: ModelSpec, task: TaskSpec) -> float` that implements `total = qw*q + lw*l + cw*c`. No I/O, no async, no shared state. The function is the heart of the framework — everything else is plumbing around it.

**Acceptance criteria:**
- [ ] AC1: `score(model, task)` returns `qw*q + lw*l + cw*c` exactly (formula matches the spec's stated formula)
- [ ] AC2: All component scores are clamped to `[0.0, 1.0]` before weighting (defensive against bad JSON data)
- [ ] AC3: If weights don't sum to `1.0` for a task, the function still works (does NOT silently renormalize — explicit weights are the contract)
- [ ] AC4: If any component score is None, that component contributes 0 (does NOT raise)
- [ ] AC5: Two models with identical scores → ties broken by `model.id` alphabetical (deterministic, no flakiness)

**Test approach:**
Pure unit tests in pytest. No fixtures needed beyond constructing `ModelSpec` and `TaskSpec` dataclasses inline. ~10 tests covering: basic formula, clamping, None handling, ties, zero weights, large weights.

**Estimated effort:** S (1-2 hours, ~50 lines source + ~100 lines tests)

---

### T-002: Backend task + model registries with JSON loader

**Files:**
- `backend/utils/auto_router/task_registry.py` (new)
- `backend/utils/auto_router/model_registry.py` (new)
- `backend/utils/auto_router/benchmarks.example.json` (new)
- `backend/tests/unit/test_auto_router_task_registry.py` (new)
- `backend/tests/unit/test_auto_router_model_registry.py` (new)

**Description:**
Two registries that hold the in-memory task and model definitions:

1. **Task registry** (`task_registry.py`): a `TaskSpec` dataclass with `name`, `quality_weight`, `latency_weight`, `cost_weight`, `description`. A `TaskRegistry` class that loads the 5 task types from a JSON file (or hardcoded defaults if file missing). Validates that weights sum to 1.0.

2. **Model registry** (`model_registry.py`): a `ModelSpec` dataclass with `id`, `quality_score`, `latency_score`, `cost_score`, `provider` (e.g., "anthropic", "openai", "google"). A `ModelRegistry` class that loads candidate models per task from a JSON file. Looks up models by ID; falls back to empty list if a task has no models in the JSON.

3. **Example data** (`benchmarks.example.json`): realistic benchmark values for 3-5 models per task. Models: `claude-sonnet-4-6`, `haiku-4-5`, `gpt-realtime-2`, `gemini-1-5-flash-8b-exp`, `parakeet-stt-v2`. Scores are educated estimates (quality/latency/cost on 0-1 scale).

**Acceptance criteria:**
- [ ] AC1: All 5 task types are defined with weights from the spec (`ptt_response`, `screenshot_understanding`, `screenshot_embedding`, `general_assistant`, `transcription`)
- [ ] AC2: `TaskRegistry.from_json(path)` loads tasks from a JSON file; missing file → use built-in defaults (not crash)
- [ ] AC3: `TaskRegistry.get(name)` returns the task; unknown name → raises `UnknownTaskError`
- [ ] AC4: Each task's weights sum to 1.0 (validated at load time)
- [ ] AC5: `ModelRegistry.from_json(path)` loads models per task; missing task entry → empty candidate list (not crash)
- [ ] AC6: `ModelRegistry.candidates_for(task_name)` returns the list of `ModelSpec`s
- [ ] AC7: `benchmarks.example.json` has at least 3 models per task with realistic scores (quality/latency/cost in [0.0, 1.0])

**Test approach:**
Unit tests in pytest. Use `tmp_path` fixture to write a small test JSON file and verify load behavior. ~12 tests: each task loads, weight validation, unknown task error, missing file fallback, JSON parsing edge cases.

**Estimated effort:** M (2-3 hours, ~150 lines source + ~150 lines tests + ~80 lines JSON)

---

### T-003: Backend daily refresh infrastructure

**Files:**
- `backend/utils/auto_router/daily_refresh.py` (new)
- `backend/tests/unit/test_auto_router_daily_refresh.py` (new)

**Description:**
A `DailyRefreshCache[T]` generic class that wraps any async loader function with:
- **24h TTL** — calls the loader at most once per 24 hours
- **`asyncio.Lock()`** — concurrent callers serialize; only one loader call fires on cache miss
- **Stale-cache fallback** — if the loader raises, return the last good value (not 500). On first-ever call with a loader error, raise (no fallback to give).

Mirrors upstream's pattern in `backend/routers/auto_model.py:_cache` and `_cache_lock`.

**Acceptance criteria:**
- [ ] AC1: `cache.get_or_refresh(loader)` returns cached value if fresh (age < 24h)
- [ ] AC2: `cache.get_or_refresh(loader)` calls loader if stale or empty
- [ ] AC3: 10 concurrent `get_or_refresh` calls with empty cache → exactly 1 loader call (lock contention test)
- [ ] AC4: Loader raising on refresh → returns last good cached value (stale fallback)
- [ ] AC5: Loader raising on first-ever call (no cached value) → propagates the exception
- [ ] AC6: `cache.age_seconds` returns seconds since last successful load (or `None` if never loaded)

**Test approach:**
Unit tests in pytest with `asyncio` and `freezegun` (or `unittest.mock.patch` for `datetime`). ~8 tests: fresh cache, stale refresh, lock contention (use `asyncio.gather` with 10 tasks), stale fallback, first-call raise.

**Estimated effort:** S (1-2 hours, ~80 lines source + ~120 lines tests)

---

### T-004: Backend FastAPI endpoint

**Files:**
- `backend/routers/auto_router.py` (new)
- `backend/tests/unit/test_auto_router_endpoint.py` (new)
- `backend/utils/auto_router/__init__.py` (extend with public exports)

**Description:**
FastAPI router exposing `GET /v1/auto-router/pick?task=<task_name>` that:
1. Loads the task spec from `TaskRegistry`
2. Loads candidate models for the task from `ModelRegistry`
3. Scores each model with `score(model, task)` from T-001
4. Returns the top-scoring model with full `scores` and `detail` payload
5. Uses `DailyRefreshCache` from T-003 to avoid re-scoring on every call

The response shape (mirrors upstream's `/v1/auto/model-pick`):
```json
{
  "task": "ptt_response",
  "model": "claude-sonnet-4-6",
  "scores": {
    "claude-sonnet-4-6": 0.82,
    "haiku-4-5": 0.74
  },
  "detail": {
    "weights": {"quality": 0.4, "latency": 0.5, "cost": 0.1},
    "candidates": [...],
    "reason": "selected claude-sonnet-4-6 (highest weighted score)"
  },
  "updated_at": "2026-06-25T10:00:00Z",
  "attribution": "mock benchmarks, see backend/utils/auto_router/benchmarks.example.json"
}
```

**Acceptance criteria:**
- [ ] AC1: `GET /v1/auto-router/pick?task=ptt_response` returns 200 with valid JSON for all 5 tasks
- [ ] AC2: `GET /v1/auto-router/pick?task=invalid` returns 400 with `{"detail": "unknown task: invalid"}`
- [ ] AC3: Response includes `task`, `model`, `scores` (all candidates), `detail` (weights + candidates + reason), `updated_at`, `attribution`
- [ ] AC4: The `model` field is the highest-scoring candidate (deterministic — ties broken by ID alphabetical)
- [ ] AC5: A second call within 24h does NOT re-score (verify by injecting a counting loader)
- [ ] AC6: Concurrent requests for the same task fire exactly 1 loader call (lock contention)
- [ ] AC7: Endpoint is importable without raising (no circular imports, all deps resolve)

**Test approach:**
Integration tests using FastAPI's `TestClient` from `fastapi.testclient`. Mock the benchmark loader to count calls. ~10 tests: happy path for each of 5 tasks, invalid task, tie-breaking, cache hit, lock contention, loader failure fallback.

**Estimated effort:** M (2-3 hours, ~120 lines source + ~150 lines tests)

---

### T-005: Backend wire-up (main.py + example benchmarks + README)

**Files:**
- `backend/main.py` (modify — add router registration)
- `backend/utils/auto_router/benchmarks.example.json` (already created in T-002; ensure present + gitignore'd copy)
- `backend/utils/auto_router/README.md` (new)

**Description:**
Three wire-up tasks that make T-001 through T-004 deployable:

1. **Register the router** in `backend/main.py`: add `from routers.auto_router import router as auto_router_router` and `app.include_router(auto_router_router)` next to the existing router registrations (`transcribe`, `conversations`, `payment`, `users`, etc.). Keep alphabetical.

2. **Provide a deployable benchmark file**: `benchmarks.example.json` is the template. For actual deployment, copy to `benchmarks.json` (which should be in `.gitignore` — add it if not). The endpoint loads `benchmarks.json` if present, falls back to `benchmarks.example.json` otherwise.

3. **Backend README**: `backend/utils/auto_router/README.md` documents how to add a task, add a model, update benchmarks, run tests, and interpret the scoring output.

**Acceptance criteria:**
- [ ] AC1: `from main import app` succeeds and `app.routes` includes the auto-router endpoint
- [ ] AC2: `benchmarks.json` is in `.gitignore` (or `.gitignore` updated to include it); if present, it's loaded; if absent, `benchmarks.example.json` is loaded
- [ ] AC3: `backend/utils/auto_router/README.md` exists with sections: Overview, Quick start, Adding a task, Adding a model, Updating benchmarks, Tests, Scoring formula reference, Daily refresh behavior, Relationship to upstream `/v1/auto/model-pick`
- [ ] AC4: Manual end-to-end test: start backend, `curl http://localhost:8000/v1/auto-router/pick?task=ptt_response` returns valid JSON

**Test approach:**
Mostly verification (run existing endpoint tests after wire-up, manually exercise the endpoint via curl). Plus a unit test for the benchmarks file resolution logic. README is markdown — no tests.

**Estimated effort:** M (1-2 hours, ~20 lines main.py + ~120 lines README + ~30 lines test)

---

### T-006: Desktop AutoRouter client

**Files:**
- `desktop/macos/Desktop/Sources/AutoRouter/AutoRouterTask.swift` (new)
- `desktop/macos/Desktop/Sources/AutoRouter/AutoRouter.swift` (new)
- `desktop/macos/Desktop/Tests/AutoRouterTests.swift` (new)

**Description:**
Mirror upstream's `AutoModelSelector.swift` pattern but for multi-task:

1. **`AutoRouterTask`** enum with 5 cases: `pttResponse`, `screenshotUnderstanding`, `screenshotEmbedding`, `generalAssistant`, `transcription`. Each maps to the backend's `task` query param value (snake_case).

2. **`AutoRouter`** singleton (matching upstream's `@MainActor final class AutoRouter { static let shared = AutoRouter() }`):
   - `pick(_ task: AutoRouterTask) -> String?` — returns the picked model ID
   - `currentPick(for task: AutoRouterTask) -> String?` — returns last cached pick without refreshing
   - `refreshIfStale(_ task: AutoRouterTask)` — async, calls `pick` if cache is >24h old
   - Internal: per-task cache in UserDefaults (`autoRouterPick.<task>`, `autoRouterPickDate.<task>`)
   - HTTP call: `GET <backend>/v1/auto-router/pick?task=<snake_case_task>` with auth header (reuses `AuthService.shared.getAuthHeader()`)
   - Fallback chain: server error → keep last good pick; first call + error → return nil (don't crash)

**Acceptance criteria:**
- [ ] AC1: `AutoRouter.shared.pick(.pttResponse)` returns a non-nil model ID after a successful endpoint call
- [ ] AC2: The picker sends the auth header (mirrors upstream `AutoModelSelector.refresh()` line 73-75)
- [ ] AC3: `AutoRouterTask.allCases` has all 5 cases; each has the correct snake_case backend name
- [ ] AC4: Per-task UserDefaults cache: 24h TTL, separate keys per task
- [ ] AC5: Network error → return last good pick (do NOT crash)
- [ ] AC6: First-ever call with network error → return nil (graceful degradation)
- [ ] AC7: Desktop tests pass: `xcrun swift test --filter AutoRouterTests` exit 0
- [ ] AC8: `xcrun swift build` exit 0, no new warnings

**Test approach:**
XCTest unit tests. For HTTP, mock `URLSession` via `URLProtocol` subclass (or use a tiny HTTP test server fixture). Pattern adapted from `AutoModelSelector.swift` usage upstream. ~8 tests: happy path, cache hit, stale refresh, auth header, network error, first-call error, enum mapping.

**Estimated effort:** M (2-3 hours, ~120 lines Swift + ~150 lines Swift tests)

---

### T-007: Developer documentation

**Files:**
- `docs/doc/developer/auto-router.md` (new)

**Description:**
High-level documentation for Omi contributors explaining the auto-router framework:

- **What it is** — task-based model selection for Omi, MVP framework, not a production routing replacement
- **Architecture** — diagram showing backend endpoint, registries, scoring, daily refresh, desktop client
- **Scoring formula** — `total = qw*q + lw*l + cw*c` with per-task weights table
- **Task types** — list of 5 supported tasks with weight rationale
- **Daily refresh mechanism** — 24h TTL + `asyncio.Lock()` + stale fallback
- **Relationship to upstream `/v1/auto/model-pick`** — explicit acknowledgment that upstream's realtime-voice picker is a special case; this is the broader framework
- **Extension guide** — how to add a new task type, add a new model, update benchmarks
- **Future work** — wiring into actual Omi paths (`ChatProvider`, `ModelQoS`, `RealtimeHubController`), real AA integration, per-user personalization

**Acceptance criteria:**
- [ ] AC1: `docs/doc/developer/auto-router.md` exists
- [ ] AC2: All 9 sections present (what, architecture, scoring, tasks, refresh, upstream relationship, extension, future work, references)
- [ ] AC3: Architecture diagram (ASCII or mermaid) shows the request flow: desktop → endpoint → registries → scoring → response
- [ ] AC4: Per-task weights table matches the spec's task definitions exactly
- [ ] AC5: Upstream relationship section names the 5 commits that ship the realtime-voice picker

**Test approach:**
No tests — markdown only. Verification: file exists, sections present, references accurate.

**Estimated effort:** S (30-60 min, ~150 lines markdown)

---

### T-008: PR polish

**Files:**
- `docs/auto-router-demo.md` (new) — 3 demo scenarios from the brief
- PR description (committed to git history, not a file)

**Description:**
Three demo scenarios from the user's brief, plus PR description polish:

1. **Low-cost mode for general assistant** — modify weights to favor cost → expect a cheap model picked
2. **High-quality mode for screenshot understanding** — modify weights to favor quality → expect a strong model picked
3. **Low-latency mode for PTT** — modify weights to favor latency → expect a fast model picked

Each demo: a small Python script that calls the endpoint with the modified weights (via a one-off test fixture or curl), shows the input weights, shows the picked model, explains why.

PR description: crafted to match the user's PR positioning notes:
- "This is a first step toward model selection across Omi"
- "It gives a framework for switching models by task based on cost/quality/latency"
- "It matches the product direction discussed"

**Acceptance criteria:**
- [ ] AC1: `docs/auto-router-demo.md` exists with 3 demo scenarios
- [ ] AC2: Each demo includes: setup (weights), call (curl or python), output (picked model + scores), interpretation
- [ ] AC3: PR description drafted (in `git commit` messages and/or notes for later PR creation)
- [ ] AC4: Final commit log is clean: spec → plan → T-001 → ... → T-008 → state=shipping, each commit has descriptive message

**Test approach:**
No automated tests. Manual verification: run the 3 demos, confirm output matches expectation.

**Estimated effort:** S (30-60 min, ~100 lines markdown + PR polish)

---

## Implementation Notes

- **Commit strategy**: 1 commit per task (T-001 through T-008) + a few `.aidlc/` metadata commits. Per repo `AGENTS.md` "individual commits per file" is satisfied within each task (source + tests paired).
- **No push, no PR** until user explicitly approves per repo `AGENTS.md`.
- **Branch is local only**: `feat/auto-router-v1` in the worktree at `/Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-v1/`.
- **Backend tests**: run via `cd backend && python -m pytest tests/unit/test_auto_router_*.py -v`.
- **Desktop tests**: run via `xcrun swift test --package-path Desktop --filter AutoRouterTests`.
- **Test framework**: XCTest (matches 44/44 desktop test files); pytest for backend.
- **Auth header reuse**: desktop client calls `AuthService.shared.getAuthHeader()` like upstream's `AutoModelSelector.refresh()` line 73-75.
- **`asyncio.Lock()` pattern**: mirrors upstream's `_cache_lock` in `backend/routers/auto_model.py:31`.
- **Benchmarks file gitignore**: `benchmarks.json` (deployment data) in `.gitignore`; `benchmarks.example.json` (template) tracked in git.

## Sizing Summary

| Task | Effort | Files | Notes |
|---|---|---|---|
| T-001 | S | 2 | Pure function, no I/O |
| T-002 | M | 5 | Two dataclasses + JSON loader + tests + example JSON |
| T-003 | S | 2 | TTL + lock pattern, mirrors upstream |
| T-004 | M | 3 | FastAPI router + integration tests + `__init__.py` exports |
| T-005 | M | 3 | main.py edit + example JSON (already created) + README |
| T-006 | M | 3 | Swift client + enum + tests |
| T-007 | S | 1 | Developer docs only |
| T-008 | S | 2 | Demo scenarios + PR polish |

Total: ~21 files, ~600 lines code + ~400 lines tests + ~250 lines docs/markdown ≈ 1,250 lines. Within the spec's ≤800-line diff budget for the framework code itself (markdown + tests are excluded from the budget).
