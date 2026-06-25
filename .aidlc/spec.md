# Auto-router v1 — Task-based model selection across Omi

## Objective

Build a **v1 auto-router** for Omi that selects the best model per task type using a configurable weighted scoring across **quality / latency / cost**. The router defines a small set of representative Omi task categories (push-to-talk response, screenshot understanding, screenshot embedding, general assistant reply, transcription), assigns candidate models to each, scores them, and returns the recommended model per task — with a daily-refreshable benchmark input flow.

This is a **foundation / MVP**, not a production routing replacement. It is intended to demonstrate the mechanism and structure the conversation Nik signaled interest in: extending dynamic model selection across Omi rather than handling model choices in isolated parts of the product.

The user-facing benefit (Nik's framing): **"an auto-router that switched EVERY ai model in omi daily to the most optimal based on value/cost benchmarks"** — applied across tasks, not just realtime voice.

## Upstream context (important — read before implementing)

The maintainer has already shipped a **narrow realtime-voice auto-router** that does similar work for ONE task type. The new MVP does NOT replace or extend it; it complements it with a broader, multi-task framework.

| Upstream has | Commit | Scope |
|---|---|---|
| `GET /v1/auto/model-pick` endpoint (backend FastAPI) | `e316decbb` | Realtime-voice only — 2 providers (`geminiFlashLive`, `gptRealtime2`) |
| `AutoModelSelector.swift` (desktop client, 188 lines) | `368523e67` | Reads the endpoint, daily cache with `applyServerPick` |
| `auto_model.py` router registration | `0ca5027ea` | Single `APIRouter` |
| Security: auth required + refresh lock + proxy slug → real AA models | `8a1c2a724`, `dcb33ea59` | Defense in depth |
| Artificial Analysis benchmark ingestion | `e316decbb` | Server-side, AA key never shipped to client |

**What this MVP adds that upstream does NOT have:**

1. **Task-type parameter** — upstream picks one model unconditionally. This MVP picks per task (ptt_response / screenshot_understanding / screenshot_embedding / general_assistant / transcription).
2. **Cost dimension** — upstream scores only `quality + speed`. This MVP scores `quality + latency + cost` with explicit weights.
3. **Per-task weights** — upstream hardcodes `0.65 / 0.35`. This MVP makes weights configurable per task (latency-heavy for PTT, quality-heavy for screenshots, cost-heavy for embeddings).
4. **Multi-domain framework** — upstream's auto-router is realtime-voice-only. This MVP covers 5 task types that today each pick independently (RealtimeHubController for voice, ModelQoS for chat, vision models for screenshot, embedding models for retrieval, STT models for transcription).
5. **Pluggable benchmark source** — mock JSON initially; future AA integration without rewrite.

**Architectural decision:** STANDALONE MVP, not an extension of `/v1/auto/model-pick`. Reasons: (a) the user's brief explicitly asks for "smallest version that already looks strategic" + "first step toward model selection across Omni" — a framework, not a tweak; (b) upstream's realtime-voice picker is tightly coupled to `RealtimeOmniProvider` (audio variants, ALPN workarounds) — absorbing other tasks into it would require a schema migration; (c) standing rule per repo `AGENTS.md` "don't duplicate upstream work" + "be honest about what's new" — a parallel implementation with explicit acknowledgment is the honest path.

Future integration is possible (the upstream auto-router could become a special case of this broader framework) but out of scope for v1.

## Commands

Per repo `backend/CLAUDE.md` and `desktop/macos/test.sh`:

```bash
# Backend tests (Python, pytest)
cd backend && python -m pytest tests/unit/test_auto_router_*.py -v

# Backend lint
cd backend && black --line-length 120 --check utils/auto_router/ routers/auto_router.py tests/unit/test_auto_router_*.py
cd backend && python scripts/scan_async_blockers.py

# Desktop build + test
cd desktop && xcrun swift build -c debug --package-path desktop/macos/Desktop
cd desktop/macos && bash test.sh

# Backend dev server (for manual testing)
cd backend && uvicorn main:app --reload --port 8000
# Then: curl http://localhost:8000/v1/auto-router/pick?task=ptt_response

# Desktop dev launch
cd desktop && OMI_APP_NAME="omi-auto-router-test" ./run.sh
```

No push / no PR until user explicitly approves (per repo `AGENTS.md`).

## Project Structure

```
backend/
├── routers/
│   └── auto_router.py                       # NEW: FastAPI router, GET /v1/auto-router/pick
├── utils/
│   └── auto_router/                         # NEW: framework package
│       ├── __init__.py
│       ├── task_registry.py                 # task definitions + per-task weights
│       ├── model_registry.py                # candidate models per task + quality/latency/cost
│       ├── scoring.py                       # weighted scoring engine
│       ├── benchmark_source.py              # JSON loader (mock; AA-ready)
│       ├── daily_refresh.py                 # TTL cache + asyncio.Lock (mirror upstream pattern)
│       ├── benchmarks.example.json          # example data
│       └── README.md                        # how to add a task / model
└── tests/
    └── unit/
        ├── test_auto_router_scoring.py       # NEW
        ├── test_auto_router_task_registry.py # NEW
        ├── test_auto_router_model_registry.py # NEW
        ├── test_auto_router_daily_refresh.py # NEW
        └── test_auto_router_endpoint.py     # NEW

desktop/macos/Desktop/
├── Sources/
│   └── AutoRouter/                           # NEW: Swift client
│       ├── AutoRouter.swift                 # multi-task picker (analogous to AutoModelSelector.swift)
│       └── AutoRouterTask.swift             # task enum
└── Tests/
    └── AutoRouterTests.swift                 # NEW

docs/
└── doc/developer/
    └── auto-router.md                        # NEW: high-level overview for contributors
```

Module name choice: `auto_router` (underscore) for the new framework, distinct from upstream's `auto_model` (singular, narrow). Endpoint at `/v1/auto-router/pick` (hyphen, distinct from upstream's `/v1/auto/model-pick`) — no namespace collision.

## Code Style

Existing patterns to follow:

**Backend router pattern** (`backend/routers/transcribe.py`):
```python
router = APIRouter()

@router.websocket("/v1/transcribe")
async def transcribe(websocket: WebSocket):
    ...
```

**Backend utility pattern** (`backend/utils/llm/providers.py`):
```python
"""LLM provider registry — exposes ModelRegistry.get(task) -> ModelSpec."""
from dataclasses import dataclass

@dataclass
class ModelSpec:
    id: str
    quality_score: float  # 0-1
    latency_score: float  # 0-1
    cost_score: float      # 0-1
```

**Desktop selector pattern** (`desktop/macos/Desktop/Sources/RealtimeOmni/AutoModelSelector.swift`):
```swift
@MainActor
final class AutoModelSelector {
    static let shared = AutoModelSelector()
    private let pickKey = "realtimeOmniAutoPick"
    private let pickDateKey = "realtimeOmniAutoPickDate"
    private let refreshInterval: TimeInterval = 24 * 60 * 60
    ...
}
```

**Do NOT do this:**
```python
# Inlining the formula — hard to test, hard to extend
def pick_model(task, models):
    return max(models, key=lambda m: m.quality * 0.6 + m.latency * 0.3 + m.cost * 0.1)
```

## Testing Strategy

| Layer | Framework | Coverage target |
|---|---|---|
| Scoring (unit) | pytest | All formula edges: ties, zeros, missing scores, NaN |
| Task registry (unit) | pytest | All 5 tasks defined; weights sum to 1.0 per task |
| Model registry (unit) | pytest | All candidate models loaded; missing-model fallback works |
| Daily refresh (unit) | pytest | TTL behavior, lock contention, stale-cache fallback |
| Endpoint (integration) | pytest + FastAPI TestClient | All 5 tasks return valid pick; invalid task → 400 |
| Desktop selector (unit) | XCTest | Enum → URL param; response → cache; auth header present |

Pre-existing test patterns to follow:
- `backend/tests/unit/test_conversation_model_split.py` — model registry testing pattern
- `desktop/macos/Desktop/Tests/CaptureScreenToolTests.swift` — source-file regex guard test pattern (for "no call site uses the old API" style checks)
- `desktop/macos/Desktop/Tests/FloatingBarSpringAnimationTests.swift` — XCTest test bundle pattern

Coverage target: 90%+ on `backend/utils/auto_router/` (the framework code); endpoint test covers happy paths for all 5 tasks.

## Boundaries

**Always do:**
- Use the weighted scoring formula `total = qw*q + lw*l + cw*c` — per-task weights defined in `task_registry.py`, NOT hardcoded in `scoring.py`
- Mirror upstream's daily-cache pattern: `asyncio.Lock()` + TTL check + stale fallback to last-good-pick
- Include unit tests with implementation
- Build the project after changes; run backend tests + desktop tests
- `git fetch upstream main` before committing — re-confirm no upstream commit landed since last check
- Individual commits per file
- Keep the PR diff ≤800 lines (larger than the 200-line cap for the small spring-animations PR, because this is a foundational framework; but still bounded)
- Commit locally only — no `git push` without explicit user approval

**Ask first:**
- Push the branch to remote
- Open a PR
- Modify upstream's `auto_model.py` or `AutoModelSelector.swift` (intentionally out of scope for v1)
- Add a new dependency (e.g., a scoring library like `numpy`)
- Wire auto-router into any actual Omi feature path (e.g., have `ChatProvider` consult the auto-router for model selection) — that's a Day-7 follow-up, not MVP scope

**Never do:**
- Touch upstream's `/v1/auto/model-pick` endpoint or `AutoModelSelector.swift` — they're intentionally untouched in v1
- Wire into the existing `RealtimeHubController` provider failover — different concern
- Wire into `ModelQoS.Claude` / `ModelQoS.Haiku` selection — different concern
- Use real AA API keys in this PR (mock JSON only — AA key handling is a follow-up)
- Auto-merge to main
- Squash-merge if/when a PR is opened (regular merge per repo `AGENTS.md`)

## Acceptance Criteria

### Backend
1. `GET /v1/auto-router/pick?task=ptt_response` returns `{"task": "ptt_response", "model": "<id>", "scores": {...}, "detail": {...}, "updated_at": <ts>}` with HTTP 200
2. Same endpoint with `task=screenshot_understanding`, `task=screenshot_embedding`, `task=general_assistant`, `task=transcription` each return valid picks (one per task type)
3. Same endpoint with `task=invalid` returns HTTP 400 with `{"detail": "unknown task: invalid"}`
4. Weights per task are loaded from `task_registry.py` and used in scoring (assertion test: changing weights in `benchmarks.example.json` changes the picked model for at least one task)
5. Daily cache: a second request within 24h does NOT re-score (verify by spying on `benchmark_source.load()`)
6. Lock contention: 10 concurrent requests for the same task result in exactly 1 `benchmark_source.load()` call (asyncio.Lock pattern)
7. Stale-cache fallback: if benchmark source raises on refresh, return last good pick (not 500)
8. Endpoint is registered in `backend/main.py` (verify by importing `main.app` and checking routes)
9. Backend tests pass: `pytest tests/unit/test_auto_router_*.py` exit 0
10. `python scripts/scan_async_blockers.py` passes (no async blockers introduced)
11. `black --check` passes on new files

### Desktop
12. `AutoRouter.shared.pick(.pttResponse)` returns a non-nil model ID after a successful endpoint call
13. The picker reads `http://<backend>/v1/auto-router/pick?task=<task>` and sends the auth header
14. Daily cache in UserDefaults: a second call within 24h does NOT re-fetch (verified by intercepting URLSession)
15. Stale-cache fallback: network error → return last good pick, do NOT crash
16. `AutoRouterTask` enum has all 5 cases matching backend task names (snake_case encoded)
17. Desktop tests pass: `xcrun swift test --filter AutoRouterTests` exit 0
18. `xcrun swift build` exit 0, no new warnings

### Documentation
19. `backend/utils/auto_router/README.md` exists with: how to add a task, how to add a model, how to update benchmarks
20. `docs/doc/developer/auto-router.md` exists with: architecture overview, scoring formula, daily refresh mechanism, relationship to upstream `/v1/auto/model-pick`
21. Example benchmarks JSON has at least 2 models per task with realistic quality/latency/cost values

### Diff hygiene
22. PR diff ≤800 lines (sum of additions across all files)
23. ≤6 commits on the branch (one per logical unit: spec, plan, scoring, registries, endpoint, refresh, desktop, docs, polish)
24. No `git push` to remote — local only — until user explicit approval

## Out of Scope

- **Wiring into existing Omi paths** — auto-router is a STANDALONE service in v1. `ChatProvider` / `ModelQoS` / `RealtimeHubController` do NOT consult it yet. That's a Day-7+ follow-up.
- **Real Artificial Analysis integration** — mock JSON only. AA key handling, rate limiting, schema migration — all follow-ups.
- **Modifying upstream `/v1/auto/model-pick`** — out of scope. Upstream's realtime-voice picker keeps working unchanged.
- **More than 5 task types** — the spec is bounded to the 5 from the brief. Adding more (e.g., "image generation", "translation") is straightforward (one line in `task_registry.py`) but not done in v1.
- **Per-user personalization** — all users get the same pick for a given task. Personalization would require user-history tracking (follow-up).
- **Online learning** — no feedback loop. Picks are pure functions of the current benchmark file.
- **Cross-task dependency** — each task picks independently. "If PTT just ran, prefer cheap model for followup" — out of scope.
- **Performance optimizations** — first request may take ~100ms (benchmark file load); cached requests are sub-ms. No pre-warming or async prefetch in v1.

## Open Questions

1. **Endpoint path**: `/v1/auto-router/pick?task=...` (chosen) vs `/v1/auto_router/pick?task=...` (underscore, but FastAPI sometimes handles underscores awkwardly) vs `/v1/auto/router/pick?task=...` (nested under upstream's `/auto/`). **Recommendation: hyphen `auto-router`** — distinct namespace, no collision with upstream, greppable.

2. **Benchmark source format**: JSON file (chosen, simple) vs YAML (more readable for human-edited benchmarks) vs SQLite (queryable but heavier). **Recommendation: JSON** — mirrors upstream's `PROXY` dict style, easy to edit, diff-friendly in PRs.

3. **Where the desktop module lives**: `desktop/macos/Desktop/Sources/AutoRouter/` (chosen) vs `desktop/macos/Desktop/Sources/RealtimeOmni/AutoRouter.swift` (next to upstream's AutoModelSelector). **Recommendation: separate folder** — different concern (multi-task vs realtime-voice), easier to maintain independently.

4. **Should this be a Python package or single files?**: Package (`backend/utils/auto_router/__init__.py` + 6 files) vs single file (`backend/utils/auto_router.py`). **Recommendation: package** — cleaner imports (`from utils.auto_router.scoring import score`), easier to test individual components.

5. **Naming the Swift class**: `AutoRouter` (chosen) vs `TaskBasedModelSelector` (descriptive but verbose) vs `OmniModelRouter` (brand-aligned). **Recommendation: `AutoRouter`** — short, matches the backend module name, mirrors upstream's `AutoModelSelector` naming style.

6. **Should the auto-router be the SINGLE source of truth for "Auto" mode in the UI?**: That is, when a user picks "Auto" in chat settings, should it go through this new router or upstream's `/v1/auto/model-pick`? **Recommendation: NOT in v1** — upstream's picker keeps handling realtime-voice "Auto"; this new router is for backend use / future wiring. Explicit separation avoids accidentally breaking the realtime-voice path.

7. **Should the spec include a 5th task type "general_speech"** (separate from `transcription` and `ptt_response`)? **Recommendation: NO** — keep to 5 task types as in the brief; "general_speech" can be added later if needed.

8. **Daily refresh TTL**: 24h (matching upstream) vs 6h (fresher but more network) vs configurable via env var. **Recommendation: 24h** — matches upstream's pattern; daily freshness is sufficient per the brief.
