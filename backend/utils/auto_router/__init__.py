"""Auto-router v1: task-based model selection across Omi.

A foundational framework (not a production routing replacement) that picks the
best model per task type using weighted scoring across quality / latency / cost.

Public API:
    ModelSpec        — a candidate model with quality/latency/cost scores (0..1).
    TaskSpec         — a task type with per-dimension weights summing to 1.0.
    score(model, task) — weighted scoring function: total = qw*q + lw*l + cw*c.
    TaskRegistry     — registry of task definitions, loads from JSON or defaults.
    ModelRegistry    — registry of candidate models per task, loads from JSON.
    DailyRefreshCache — TTL + asyncio.Lock + stale-fallback cache wrapper.
    router (in routers/auto_router.py) — FastAPI endpoint exposing /v1/auto-router/pick.

The desktop client (desktop/macos/Desktop/Sources/AutoRouter/AutoRouter.swift)
is part of v1 as well. v2 adds auth, observability, and chat wiring.
See `backend/utils/auto_router/README.md` for the full architecture.

Relationship to upstream `/v1/auto/model-pick`:
    The maintainer's narrow realtime-voice auto-router (see
    `backend/routers/auto_model.py`) handles ONE task (realtime voice, with
    two providers: geminiFlashLive, gptRealtime2). This package is a broader
    framework covering FIVE task types with a richer scoring formula
    (quality + latency + cost, with per-task weights). v1 does NOT modify
    or extend the upstream auto-router.
"""

from utils.auto_router.daily_refresh import DailyRefreshCache
from utils.auto_router.model_registry import (
    ModelRegistry,
    ModelValidationError,
)
from utils.auto_router.scoring import ModelSpec, TaskSpec, score
from utils.auto_router.task_registry import (
    TaskRegistry,
    TaskValidationError,
    UnknownTaskError,
)

__all__ = [
    # Scoring (T-001)
    "ModelSpec",
    "TaskSpec",
    "score",
    # Registries (T-002)
    "TaskRegistry",
    "ModelRegistry",
    "UnknownTaskError",
    "TaskValidationError",
    "ModelValidationError",
    # Daily refresh (T-003)
    "DailyRefreshCache",
]
