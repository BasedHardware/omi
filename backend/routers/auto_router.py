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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from utils.auto_router.daily_refresh import DailyRefreshCache
from utils.auto_router.model_registry import ModelRegistry
from utils.auto_router.scoring import ModelSpec, TaskSpec, score
from utils.auto_router.task_registry import TaskRegistry, UnknownTaskError
from utils.executors import run_blocking

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
async def auto_router_pick(task: str = Query(..., description="Task name to pick a model for")):
    """Return the recommended model for `task` plus full scoring detail.

    Returns HTTP 400 if `task` is not a known task name.
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

    # Score candidates.
    candidates = model_registry.candidates_for(task)
    scored: List[tuple[ModelSpec, float]] = [(model, score(model, task_spec)) for model in candidates]
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
                "quality": task_spec.quality_weight,
                "latency": task_spec.latency_weight,
                "cost": task_spec.cost_weight,
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
    }
    return response


def reset_registry_cache_for_testing() -> None:
    """Clear the module-level registry cache. Test-only helper."""
    global _registry_cache
    _registry_cache = None
