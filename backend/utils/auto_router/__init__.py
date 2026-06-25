"""Auto-router v1: task-based model selection across Omi.

A foundational framework (not a production routing replacement) that picks the
best model per task type using weighted scoring across quality / latency / cost.

Public API:
    ModelSpec        — a candidate model with quality/latency/cost scores (0..1).
    TaskSpec         — a task type with per-dimension weights summing to 1.0.
    score(model, task) — weighted scoring function: total = qw*q + lw*l + cw*c.

The registries (TaskRegistry, ModelRegistry), daily refresh cache, FastAPI
router, and desktop client are added in subsequent AIDLC tasks. See
`backend/utils/auto_router/README.md` for the full architecture.

Relationship to upstream `/v1/auto/model-pick`:
    The maintainer's narrow realtime-voice auto-router (see
    `backend/routers/auto_model.py`) handles ONE task (realtime voice, with
    two providers: geminiFlashLive, gptRealtime2). This package is a broader
    framework covering FIVE task types with a richer scoring formula
    (quality + latency + cost, with per-task weights). v1 does NOT modify
    or extend the upstream auto-router.
"""

from utils.auto_router.scoring import ModelSpec, TaskSpec, score

__all__ = ["ModelSpec", "TaskSpec", "score"]
