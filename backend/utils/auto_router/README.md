# Auto-router v1 — backend framework

A foundational framework for **task-based model selection** across Omi. Picks the best model per task type using a weighted scoring across **quality / latency / cost**.

This is a **foundation / MVP**, not a production routing replacement. It demonstrates the mechanism and structures the conversation Nik signaled interest in: extending dynamic model selection across Omi rather than handling model choices in isolated parts of the product.

> **Relationship to upstream `/v1/auto/model-pick`:** The maintainer has shipped a narrower auto-router at `backend/routers/auto_model.py` that handles ONE task (realtime voice, with two providers). This package is a broader framework covering FIVE task types with a richer scoring formula. v1 does NOT modify or extend the upstream auto-router.

## Quick start

The endpoint is registered automatically when `backend/main.py` is loaded:

```bash
# Start the backend
cd backend && uvicorn main:app --reload --port 8000

# Hit the pick endpoint (auth required — pass a Bearer token)
curl -H "Authorization: Bearer <your-firebase-token>" \
     "http://localhost:8000/v1/auto-router/pick?task=ptt_response"

# Metrics endpoint (auth required)
curl -H "Authorization: Bearer <your-firebase-token>" \
     "http://localhost:8000/v1/auto-router/metrics"

# Per-user prefs (auth required)
curl -H "Authorization: Bearer <your-firebase-token>" \
     "http://localhost:8000/v1/auto-router/prefs"

# Admin force-refresh (requires X-Admin-Key header)
curl -X POST -H "X-Admin-Key: $ADMIN_KEY" \
     "http://localhost:8000/v1/auto-router/refresh-benchmarks"
```

If you have a real `benchmarks.json` (deployment data), the endpoint loads it. Otherwise it falls back to `benchmarks.example.json` (template, committed). The fallback is logged at INFO level.

> **v2 note:** Both endpoints now require an `Authorization: Bearer <token>` header (matches upstream's `/v1/auto/model-pick`). The token is validated via the upstream `get_current_user_uid` helper; the `uid` is captured but not used in v2 (per-user prefs is v3).

## Environment variables

| Var | Required? | Effect |
|---|---|---|
| `AA_API_KEY` | No | Enables live benchmarks from `https://artificialanalysis.ai/api/v2/data/llms/models` (LLM tasks only). If unset, the fetcher falls back to `benchmarks.example.json` and logs WARNING. Get a key at https://artificialanalysis.ai/api. |
| `ADMIN_KEY` | No | Enables the admin-only `POST /v1/auto-router/refresh-benchmarks` endpoint. If unset, the endpoint returns 503 (admin disabled). When set, callers must send `X-Admin-Key: <ADMIN_KEY>` header. |
| `AA_CACHE_PATH` | No | Override the cache file path (default: `backend/utils/auto_router/benchmarks.json`, gitignored). Useful for tests. |

### v3 fallback chain

Benchmarks are loaded in this priority (highest first):

1. **`benchmarks.json`** if present and <24h old → use cached AA response
2. **`AA_API_KEY` set + cache stale/empty** → fetch from AA, write to `benchmarks.json`
3. **Any failure** (no key, AA unreachable, malformed JSON) → fall back to `benchmarks.example.json` + log WARNING

STT and embedding tasks (transcription, screenshot_embedding) are NOT covered by AA — they always come from `benchmarks.example.json` regardless of source.

> **v3 note:** Both pick and metrics endpoints require auth. Per-user prefs endpoints (GET/PUT `/prefs`) also require auth. Admin refresh requires `X-Admin-Key` (separate from user auth).

## Supported task types (v1)

| Task | quality | latency | cost | Why these weights |
|---|---|---|---|---|
| `ptt_response` | 0.4 | 0.5 | 0.1 | Real-time voice — latency-critical |
| `screenshot_understanding` | 0.6 | 0.2 | 0.2 | Vision-language — quality-critical |
| `screenshot_embedding` | 0.2 | 0.3 | 0.5 | Bulk retrieval — cost-critical |
| `general_assistant` | 0.5 | 0.3 | 0.2 | Balanced for general chat |
| `transcription` | 0.3 | 0.6 | 0.1 | STT — latency-critical |

These are the v1 starting points. Tune per your workload; the scoring function applies weights exactly as specified (no renormalization).

> **⚠️ The example model scores in `benchmarks.example.json` are EDUCATED ESTIMATES** — not measured benchmarks. They are illustrative numbers to make the framework runnable out of the box. For production deployment, replace `benchmarks.json` with real measurements (e.g., from Artificial Analysis for LLM providers, in-house benchmarks for STT/embedding).

## Scoring formula

For a candidate model `m` and task `t`:

```
total = t.quality_weight * m.quality_score
      + t.latency_weight * m.latency_score
      + t.cost_weight    * m.cost_score
```

All component scores are clamped to `[0.0, 1.0]` before weighting. `None` for any score is treated as `0` (a model not benchmarked for a dimension doesn't get a free pass on it).

The picker returns the highest-scoring model for the task; ties are broken by `model.id` alphabetical (deterministic).

## Adding a new task

1. Edit `benchmarks.example.json` (template) and `benchmarks.json` (your deployment copy) — add a new task entry:
   ```json
   {
     "name": "image_generation",
     "quality_weight": 0.7,
     "latency_weight": 0.2,
     "cost_weight": 0.1,
     "description": "Generate images from text prompts. Quality-critical."
   }
   ```
2. Add candidate models under `models.image_generation`.
3. Weights must sum to 1.0 (±0.001 tolerance). Otherwise loading fails with `TaskValidationError`.

## Adding a new model

Edit the benchmarks JSON — add the model to the candidate list for one or more tasks:

```json
{
  "id": "claude-opus-5",
  "provider": "anthropic",
  "quality_score": 0.98,
  "latency_score": 0.50,
  "cost_score": 0.20
}
```

Scores are normalized to `[0.0, 1.0]` (1.0 = best in class). The scoring function clamps out-of-range values silently — but better to fix the source data.

## Daily refresh

The endpoint caches both registries (TaskRegistry + ModelRegistry) in a `DailyRefreshCache` with a **24-hour TTL** and `asyncio.Lock()`. Behavior:

- First call after startup (or after 24h) loads both registries from the benchmarks JSON.
- Concurrent calls serialize on the lock; only the first caller hits disk; subsequent callers wait and read the freshly-loaded value.
- If the loader raises (e.g., disk error, malformed JSON): returns the last good value (degraded mode, logged at WARNING) if present, else propagates the exception.

This mirrors the upstream pattern in `backend/routers/auto_model.py` for consistency.

## Architecture

```
backend/utils/auto_router/
├── __init__.py              # public API exports
├── scoring.py               # ModelSpec, TaskSpec, score()
├── task_registry.py         # TaskRegistry (loads from JSON or defaults)
├── model_registry.py        # ModelRegistry (loads from JSON, empty default)
├── daily_refresh.py         # DailyRefreshCache[T] generic cache
├── benchmarks.example.json  # template data (committed, NOT real benchmarks)
└── README.md                # this file

backend/routers/auto_router.py   # FastAPI router, GET /v1/auto-router/pick

backend/tests/unit/
├── test_auto_router_scoring.py
├── test_auto_router_task_registry.py
├── test_auto_router_model_registry.py
├── test_auto_router_daily_refresh.py
└── test_auto_router_endpoint.py
```

## Endpoint response shape

```json
{
  "task": "ptt_response",
  "model": "gemini-1-5-flash-8b-exp",
  "scores": {
    "gemini-1-5-flash-8b-exp": 0.715,
    "gpt-realtime-2": 0.78,
    "claude-sonnet-4-6": 0.658,
    "haiku-4-5": 0.778
  },
  "detail": {
    "weights": {"quality": 0.4, "latency": 0.5, "cost": 0.1},
    "candidates": [
      {"id": "gpt-realtime-2", "provider": "openai", "scores": {"quality": 0.85, "latency": 0.80, "cost": 0.60}},
      ...
    ],
    "reason": "selected haiku-4-5 (highest weighted score 0.7780)"
  },
  "updated_at": "2026-06-25T10:00:00Z",
  "attribution": "Mock benchmarks for development. See backend/utils/auto_router/benchmarks.example.json for the data format. Production deployment should use real measurements."
}
```

## Tests

```bash
cd backend && PYENV_VERSION=3.11.11 python -m pytest tests/unit/test_auto_router_*.py -v
```

118 tests across 6 files:

- `test_auto_router_scoring.py` (40) — formula, clamping, None handling, determinism, weight validation (NaN/inf/negative/bool/str rejected)
- `test_auto_router_task_registry.py` (21) — defaults, lookups, validation, JSON loading
- `test_auto_router_model_registry.py` (16) — empty, lookups, JSON loading
- `test_auto_router_daily_refresh.py` (13) — TTL, lock contention, stale fallback
- `test_auto_router_endpoint.py` (20) — happy path (5 tasks), invalid task, scores completeness, no-candidates → null, HTTP method/route handling
- `test_auto_router_demo.py` (8) — integration test that runs the demo script and verifies expected picks

## Performance characteristics

Run from the backend directory:

```bash
cd backend && PYENV_VERSION=3.11.11 python -m utils.auto_router.benchmark
```

Measured on macOS Darwin, Python 3.12.8, single-threaded:

| Metric | Value | Notes |
|---|---|---|
| Per-candidate `score()` call | ~135 ns | Pure-function overhead; CPU-bound |
| Full warm endpoint request (5 tasks × all candidates) | ~2.7 µs | After cache is primed; JSON serialization excluded |
| Cold first request (registry load from disk) | ~235 µs | One-time cost; cached for 24h after |
| `benchmarks.json` file size | ~3 KB | JSON parse is fast |

**Net:** Scoring is microseconds. Response time is dominated by network I/O and FastAPI's JSON serialization, NOT by the scoring function. No optimization needed for v1.

## Out of scope (v1)

- **Wiring into `ChatProvider`, `ModelQoS`, `RealtimeHubController`** — the router is standalone; the existing Omi code paths do not consult it. That's a Day-7+ follow-up.
- **Real Artificial Analysis integration** — `benchmarks.json` is the source. AA key handling is a follow-up.
- **Modifying upstream `/v1/auto/model-pick`** — out of scope. Upstream's realtime-voice picker keeps working unchanged.
- **Per-user personalization** — all users get the same pick for a given task.
- **Online learning** — no feedback loop. Picks are pure functions of the current benchmarks file.

## References

- Spec: `.aidlc/spec.md`
- Plan: `.aidlc/plan.md`
- AIDLC state: `.aidlc/state.md`
- Upstream auto-router (DO NOT MODIFY): `backend/routers/auto_model.py`
- Upstream desktop client (DO NOT MODIFY): `desktop/macos/Desktop/Sources/RealtimeOmni/AutoModelSelector.swift`
