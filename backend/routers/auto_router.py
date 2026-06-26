"""FastAPI router exposing the auto-router's pick endpoint.

`GET /v1/auto-router/pick?task=<task_name>` returns the highest-scoring model
for the given task, along with full scoring detail (per-candidate scores,
weights, attribution).

Architecture:
    - On first request (or app startup), load TaskRegistry + ModelRegistry from
      the configured JSON file (or use built-in defaults / empty registry).
    - The combined pick result is wrapped in a DailyRefreshCache so repeated
      calls within 24h don't re-compute scores (although scoring is fast — the
      cache is mostly there for symmetry with upstream's `/v1/auto/model-pick`).
    - Score computation: `score(model, task)` from `utils.auto_router.scoring`.

Endpoint response shape:
    {
      "task": "ptt_response",
      "model": "claude-sonnet-4-6",          // or null if no candidates
      "scores": {"<model_id>": 0.82, ...},   // all candidates, sorted desc
      "detail": {
        "weights": {"quality": 0.4, "latency": 0.5, "cost": 0.1},
        "candidates": [{"id": "...", "provider": "...", "scores": {...}}, ...],
        "reason": "selected <model_id> (highest weighted score)"
      },
      "updated_at": "2026-06-25T10:00:00Z",
      "attribution": "mock benchmarks, see backend/utils/auto_router/benchmarks.example.json"
    }

Distinct from upstream `/v1/auto/model-pick`:
    - Upstream handles ONE task (realtime voice, 2 providers, AA-backed).
    - This router handles FIVE task types with configurable per-task weights.
    - This router is for FUTURE wiring; v1 is standalone (see spec for rationale).
"""

import logging
import os
import json
import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from utils.auto_router.daily_refresh import DailyRefreshCache
from utils.auto_router.metrics import MetricsCollector
from utils.auto_router.model_registry import ModelRegistry
from utils.auto_router.scoring import ModelSpec, TaskSpec, score
from utils.auto_router.task_registry import TaskRegistry, UnknownTaskError
from utils.auto_router.user_prefs import UserPrefs
from utils.auto_router.prefs_store_factory import (
    get_user_prefs_store as _factory_get_user_prefs_store,
    reset_user_prefs_store_for_testing as _factory_reset_user_prefs_store,
)
from utils.auto_router.user_prefs import TaskWeights
from utils.executors import run_blocking

# Module-level metrics collector singleton. Reset between tests via
# reset_metrics_collector_for_testing().
_metrics_collector = MetricsCollector()

# Auth: use a thin local wrapper instead of importing get_current_user_uid
# at module level. The upstream auth function pulls in firebase_admin + stripe
# + redis, which are heavy deps not needed for the auto-router unit tests
# (we override this dependency with a test uid in the test fixture).
# In production, the lazy import in `auth_dependency` resolves to the real
# upstream function.
_DEFAULT_TEST_UID = "test-uid"


def auth_dependency(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency for the auto-router endpoints.

    Lazy-imports the upstream `get_current_user_uid` so the unit tests don't
    need firebase_admin. In production, this delegates to the real auth
    function (which validates the Firebase token, records the user's platform,
    and validates BYOK headers). In tests, the dependency is overridden with
    a lambda that returns a test uid.

    The `Header(None)` annotation is required: without it, FastAPI would treat
    `authorization` as a query parameter (not the Authorization header), which
    would break parity with upstream endpoints. The upstream function
    `get_current_user_uid` itself declares `authorization: str = Header(None)`,
    so we must mirror that.
    """
    from utils.other.endpoints import get_current_user_uid  # lazy

    return get_current_user_uid(authorization=authorization)


logger = logging.getLogger(__name__)


# Path resolution: prefer benchmarks.json (deployment data) if present,
# otherwise benchmarks.example.json (template tracked in git).
# File layout: <repo>/backend/routers/auto_router.py — `parents[1]` is `backend/`.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BENCHMARKS_JSON = _BACKEND_ROOT / "utils" / "auto_router" / "benchmarks.json"
_DEFAULT_BENCHMARKS_EXAMPLE = _BACKEND_ROOT / "utils" / "auto_router" / "benchmarks.example.json"
_ATTRIBUTION = (
    "Mock benchmarks for development. See "
    "backend/utils/auto_router/benchmarks.example.json for the data format. "
    "Production deployment should use real measurements (e.g., from Artificial "
    "Analysis for LLMs, in-house benchmarks for STT/embedding)."
)


router = APIRouter()


# ---------------------------------------------------------------------------
# Lazy-loaded registries (cached for the lifetime of the process)
# ---------------------------------------------------------------------------


_registry_cache: Optional[DailyRefreshCache[tuple[TaskRegistry, ModelRegistry]]] = None


def _load_registries() -> tuple[TaskRegistry, ModelRegistry]:
    """Load both registries from disk. Used as the cache loader."""
    benchmark_path = _DEFAULT_BENCHMARKS_JSON
    if not benchmark_path.exists():
        benchmark_path = _DEFAULT_BENCHMARKS_EXAMPLE
        logger.info(f"auto_router: benchmarks.json not found, using example template {benchmark_path}")
    tasks = TaskRegistry.from_json(benchmark_path)
    models = ModelRegistry.from_json(benchmark_path)
    return tasks, models


# Wrap the file I/O in a threadpool to avoid blocking the event loop.
# Per repo CLAUDE.md: never call sync DB/storage/file functions directly inside
# async def — wrap with `await run_blocking(sync_executor, ...)`.
_load_registries_async = None  # set lazily so we don't require executors at import time


def _get_loader():
    """Return an async loader that runs the sync file I/O in a threadpool."""
    from utils.executors import sync_executor

    global _load_registries_async
    if _load_registries_async is None:

        async def _async_load():
            return await run_blocking(sync_executor, _load_registries)

        _load_registries_async = _async_load
    return _load_registries_async


def _get_registry_cache() -> DailyRefreshCache[tuple[TaskRegistry, ModelRegistry]]:
    """Return the process-wide registry cache, creating it on first access."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = DailyRefreshCache(ttl_seconds=24 * 60 * 60)  # 24h
    return _registry_cache


# ---------------------------------------------------------------------------
# Pick endpoint
# ---------------------------------------------------------------------------


@router.get("/v1/auto-router/pick")
async def auto_router_pick(
    task: str = Query(..., description="Task name to pick a model for"),
    uid: str = Depends(auth_dependency),
    weights: Optional[str] = Query(
        None,
        description=(
            "Optional JSON-encoded weight override for this call only "
            "(does NOT update stored prefs). Format: "
            '{"quality": 0.4, "latency": 0.4, "cost": 0.2}. '
            "Used by demo scripts + testing."
        ),
    ),
):
    """Return the recommended model for `task` plus full scoring detail.

    Requires authentication (matches upstream's `/v1/auto/model-pick`).
    The `uid` is used to look up the user's stored per-task weight overrides
    (v3). If the user has overrides for this task, they take precedence over
    the task's default weights. Pass `weights=...` to override the stored
    prefs for THIS call only (does NOT update stored prefs).

    Returns HTTP 400 if `task` is not a known task name.
    Returns HTTP 400 if `weights` is invalid JSON / doesn't sum to 1.0.
    """
    cache = _get_registry_cache()

    task_registry, model_registry = await cache.get_or_refresh(_get_loader())

    # Validate task.
    try:
        task_spec = task_registry.get(task)
    except UnknownTaskError:
        # Note: don't leak the full list of known task names in the response
        # body — clients can enumerate them via probing. The list is in the
        # public docs anyway (`docs/doc/developer/auto-router.mdx`).
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unknown_task",
                "message": f"unknown task: {task!r}",
                "docs": "see docs/doc/developer/auto-router.mdx#supported-task-types-v1",
            },
        )

    # Resolve effective weights for this task. Priority (highest first):
    #   1. Query param `weights` (if provided) — call-only override
    #   2. User's stored prefs (looked up by uid)
    #   3. Task default weights
    if weights is not None:
        try:
            parsed = json.loads(weights)
            override_weights = TaskWeights(
                quality=float(parsed["quality"]),
                latency=float(parsed["latency"]),
                cost=float(parsed["cost"]),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_weights",
                    "message": f"invalid weights query param: {e}",
                },
            )
        effective_weights = override_weights
        weights_source = "query_param"
    else:
        store = _factory_get_user_prefs_store()
        stored = store.get(uid)
        defaults = {
            task_spec.name: TaskWeights(
                quality=task_spec.quality_weight,
                latency=task_spec.latency_weight,
                cost=task_spec.cost_weight,
            )
        }
        merged = stored.prefs.merged_with(defaults)
        effective_weights = merged[task_spec.name]
        weights_source = "user_prefs" if task_spec.name in stored.prefs.overrides else "task_default"

    # Score candidates using the effective weights. We construct a TaskSpec
    # on the fly with the effective weights so we can reuse the canonical
    # `score(model, task)` function (same clamping + None handling).
    effective_task_spec = TaskSpec(
        name=task_spec.name,
        quality_weight=effective_weights.quality,
        latency_weight=effective_weights.latency,
        cost_weight=effective_weights.cost,
        description=task_spec.description,
    )
    candidates = model_registry.candidates_for(task)
    scored: List[tuple[ModelSpec, float]] = [(model, score(model, effective_task_spec)) for model in candidates]
    # Sort by score desc, then by id asc for deterministic tie-breaking.
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))

    # Pick the winner (None if no candidates).
    winner: Optional[ModelSpec] = scored[0][0] if scored else None
    winner_score: Optional[float] = scored[0][1] if scored else None

    # updated_at should reflect when the BENCHMARKS were last loaded (not the
    # current response time) — that's what the consumer cares about for
    # "is this data fresh?". DailyRefreshCache exposes last_loaded_wall_time().
    cache_last_loaded = cache.last_loaded_wall_time()

    # Build response.
    response: Dict[str, Any] = {
        "task": task_spec.name,
        "model": winner.id if winner else None,
        "scores": {model.id: s for model, s in scored},
        "detail": {
            "weights": {
                "quality": effective_task_spec.quality_weight,
                "latency": effective_task_spec.latency_weight,
                "cost": effective_task_spec.cost_weight,
            },
            "candidates": [
                {
                    "id": m.id,
                    "provider": m.provider,
                    "scores": {
                        "quality": m.quality_score,
                        "latency": m.latency_score,
                        "cost": m.cost_score,
                    },
                }
                for m, _ in scored
            ],
            "reason": (
                f"selected {winner.id} (highest weighted score {winner_score:.4f})"
                if winner
                else "no candidates registered for this task"
            ),
        },
        "updated_at": (
            cache_last_loaded.isoformat().replace("+00:00", "Z")
            if cache_last_loaded is not None
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "attribution": _ATTRIBUTION,
        "weights_source": weights_source,  # "query_param" | "user_prefs" | "task_default"
    }

    # Record this pick in the metrics history (process-local, in-memory).
    # v3 may persist this to Redis/DB. Use effective weights (which may differ
    # from task_spec defaults if user prefs or ?weights= override is active).
    if winner is not None and winner_score is not None:
        _metrics_collector.record_pick(
            task=task_spec.name,
            model=winner.id,
            score=winner_score,
            weights_used={
                "quality": effective_task_spec.quality_weight,
                "latency": effective_task_spec.latency_weight,
                "cost": effective_task_spec.cost_weight,
            },
        )

    return response


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------


@router.get("/v1/auto-router/metrics")
async def auto_router_metrics(
    uid: str = Depends(auth_dependency),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
):
    """Expose cache state, per-task current state, and pick history.

    Requires authentication (matches pick endpoint).
    The `uid` is captured but not used in v2 (per-user metrics is v3).

    Process-local only — pick_history is in-memory and resets on restart.

    Admin gating (cubic review): pick_history exposes *global* in-memory
    state across ALL users. Any authenticated user shouldn't see other
    users' picks. When ADMIN_KEY is configured, callers must present
    it via X-Admin-Key (constant-time comparison). When ADMIN_KEY is
    unset (default in dev/test), pick_history is open to all callers —
    matches the dev workflow + keeps tests simple. Production
    deployments should always set ADMIN_KEY.
    """
    # Admin gate (cubic review P1 — second pass): pick_history is now
    # ALWAYS admin-gated, even when ADMIN_KEY is unset. The previous
    # fail-open behavior (open when ADMIN_KEY unset) is a configuration
    # drift risk: if an operator forgets to set ADMIN_KEY in production,
    # every authenticated user could see every other user's pick history.
    # The new behavior: when ADMIN_KEY is unset, treat that as "auth not
    # configured" and return empty pick_history (with a flag). Operators
    # MUST set ADMIN_KEY to enable pick_history visibility.
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    admin_configured = bool(admin_key)
    is_admin = (
        admin_configured
        and x_admin_key is not None
        and hmac.compare_digest(
            x_admin_key.strip().encode("utf-8"),
            admin_key.encode("utf-8"),
        )
    )

    cache = _get_registry_cache()
    task_registry, model_registry = await cache.get_or_refresh(_get_loader())

    state = _metrics_collector.current_state(task_registry, model_registry, cache)
    # pick_history exposes global state across ALL users. Only include it
    # for admin callers (cubic review). When ADMIN_KEY is unset, pick_history
    # is open (dev-friendly). When set, non-admin callers get an empty list +
    # a flag indicating admin is required.
    if is_admin:
        state["pick_history"] = _metrics_collector.pick_history_snapshot()
    else:
        # Admin-gated (cubic review P1): default-closed. Either the
        # operator needs to configure ADMIN_KEY, or the caller needs to
        # provide the correct key. Either way, we don't leak the global
        # pick history to every authenticated caller.
        state["pick_history"] = []
        if admin_configured:
            state["pick_history_admin_required"] = True
        else:
            state["pick_history_admin_not_configured"] = True
    state["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # v3: report where the benchmarks came from (AA live data vs example mock).
    benchmarks_source, benchmarks_last_refresh = _benchmarks_source_and_refresh()
    state["benchmarks_source"] = benchmarks_source
    state["benchmarks_last_refresh"] = benchmarks_last_refresh

    return state


# ---------------------------------------------------------------------------
# Per-user prefs endpoints (v3)
# ---------------------------------------------------------------------------


@router.get("/v1/auto-router/prefs")
async def auto_router_get_prefs(uid: str = Depends(auth_dependency)):
    """Return the current user's per-task weight overrides.

    Empty prefs (the default) means the user has not set any overrides;
    the picker uses task defaults. Response shape:

        {
          "uid": "<uid>",
          "prefs": {"<task_name>": {"quality": ..., "latency": ..., "cost": ...}, ...},
          "updated_at": "2026-06-25T12:00:00Z"   // ISO 8601, null if never set
        }

    Requires authentication (matches `/pick`).
    """
    store = _factory_get_user_prefs_store()
    entry = store.get(uid)
    updated_at_iso = (
        datetime.fromtimestamp(entry.updated_at, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if entry.updated_at > 0.0
        else None
    )
    return {
        "uid": uid,
        "prefs": entry.prefs.to_dict(),
        "updated_at": updated_at_iso,
    }


@router.put("/v1/auto-router/prefs")
async def auto_router_set_prefs(
    body: Dict[str, Any],
    uid: str = Depends(auth_dependency),
):
    """Set the current user's per-task weight overrides.

    Request body shape:
        {
          "prefs": {
            "<task_name>": {"quality": ..., "latency": ..., "cost": ...},
            ...
          }
        }

    Each task's weights must sum to 1.0 (tolerance 1e-3, matches TaskSpec).
    Empty `prefs: {}` clears all overrides (returns empty prefs).

    Returns 200 with the updated prefs and `updated_at`.
    Returns 400 if any task's weights are invalid.
    """
    if "prefs" not in body:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_prefs",
                "message": "request body must include 'prefs' key",
            },
        )

    raw_prefs = body["prefs"]
    if raw_prefs is None:
        raw_prefs = {}
    if not isinstance(raw_prefs, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_prefs_type",
                "message": f"'prefs' must be a dict, got {type(raw_prefs).__name__}",
            },
        )

    # Parse + validate. UserPrefs.from_dict raises ValueError/TypeError on bad input.
    try:
        prefs = UserPrefs.from_dict(raw_prefs)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_prefs",
                "message": str(e),
            },
        )

    # Persist.
    store = _factory_get_user_prefs_store()
    entry = store.set(uid, prefs)
    return {
        "uid": uid,
        "prefs": entry.prefs.to_dict(),
        "updated_at": datetime.fromtimestamp(entry.updated_at, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------------------------------------------------------------------------
# Admin endpoints (v3)
# ---------------------------------------------------------------------------


def _benchmarks_source_and_refresh() -> tuple:
    """Return (source, refreshed_at_iso) for the metrics endpoint."""
    from utils.auto_router.benchmarks_fetcher import get_benchmarks_fetcher

    fetcher = get_benchmarks_fetcher()
    cache_path = Path(fetcher._cache_path)  # noqa: SLF001
    if cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            refreshed_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            return "aa", refreshed_iso
        except OSError:
            pass
    return "example", None


@router.post("/v1/auto-router/refresh-benchmarks")
async def auto_router_refresh_benchmarks(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
):
    """Force-refresh the benchmarks cache from Artificial Analysis."""
    expected_key = os.environ.get("ADMIN_KEY", "").strip()
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "admin_not_configured",
                "message": "ADMIN_KEY env var is not set; admin endpoints are disabled",
            },
        )
    # Use `hmac.compare_digest` for constant-time comparison. Plain `==`
    # short-circuits on the first differing byte, leaking length-prefix
    # info via response timing. Low-severity (admin-only endpoint, 503
    # when ADMIN_KEY is unset by default) but idiomatic to fix.
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.strip().encode("utf-8"),
        expected_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_admin_key", "message": "X-Admin-Key header is missing or invalid"},
        )

    from utils.auto_router.benchmarks_fetcher import get_benchmarks_fetcher

    fetcher = get_benchmarks_fetcher()
    try:
        data, source, refreshed_at = await fetcher.fetch(force=True)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"code": "refresh_failed", "message": f"benchmarks refresh failed: {type(e).__name__}: {e}"},
        )

    task_count = len(data.get("tasks", []))
    model_count = sum(len(candidates) for candidates in data.get("models", {}).values())
    return {
        "status": "ok",
        "source": source,
        "fetched_at": refreshed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "task_count": task_count,
        "model_count": model_count,
    }


def reset_registry_cache_for_testing() -> None:
    """Clear the module-level registry cache. Test-only helper."""
    global _registry_cache
    _registry_cache = None


def reset_metrics_collector_for_testing() -> None:
    """Reset the metrics collector (clears pick history). Test-only helper."""
    from utils.auto_router.metrics import MetricsCollector, PickHistory

    global _metrics_collector
    _metrics_collector = MetricsCollector(PickHistory())


def reset_user_prefs_store_for_endpoint_testing() -> None:
    """Reset the user prefs store singleton. Test-only helper."""
    _factory_reset_user_prefs_store()


def reset_benchmarks_fetcher_for_endpoint_testing() -> None:
    """Reset the benchmarks fetcher singleton. Test-only helper."""
    from utils.auto_router.benchmarks_fetcher import reset_benchmarks_fetcher_for_testing

    reset_benchmarks_fetcher_for_testing()
