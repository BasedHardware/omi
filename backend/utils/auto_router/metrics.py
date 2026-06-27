"""Metrics collection for the auto-router.

Provides:
- `PickHistory`: thread-safe ring buffer (capped at 100 entries) that records
  each successful model pick made by the endpoint. In-memory only (not
  persistent) — v3 may add Redis/DB persistence.

- `MetricsCollector`: singleton that owns the PickHistory and exposes
  `record_pick(...)`, `pick_history_snapshot()`, and `current_state(...)`.
  Wired into the endpoint: pick endpoint calls `record_pick` after computing
  the winner; metrics endpoint reads `current_state` + `pick_history_snapshot`.

Why a singleton: simple, no DI complexity, matches the upstream pattern
of module-level caches. The pick endpoint and metrics endpoint both live
in the same process; the singleton is the natural shared state.

Thread-safety: `record_pick` and `pick_history_snapshot` are protected by
a `threading.Lock`. The endpoint may be hit by multiple concurrent
FastAPI workers (threadpool) + async tasks. The deque operations themselves
are atomic in CPython, but we lock for explicit correctness.
"""

import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.auto_router.daily_refresh import DailyRefreshCache
from utils.auto_router.model_registry import ModelRegistry
from utils.auto_router.task_registry import TaskRegistry

# Cap the pick history to bound memory. 100 picks × ~200 bytes = ~20 KB max.
MAX_PICK_HISTORY = 100


@dataclass(frozen=True)
class PickRecord:
    """One successful pick made by the endpoint."""

    timestamp: str  # ISO 8601 with 'Z' suffix (UTC)
    task: str
    model: str
    score: float
    weights_used: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PickHistory:
    """Thread-safe ring buffer of PickRecords, capped at MAX_PICK_HISTORY entries.

    Newest records are at the END of the list (most recent first when
    iterated in reverse, or oldest first when iterated forward).
    """

    def __init__(self, max_size: int = MAX_PICK_HISTORY) -> None:
        if max_size <= 0:
            raise ValueError(f"max_size must be > 0, got {max_size}")
        self._max_size = max_size
        self._records: deque[PickRecord] = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def record(self, record: PickRecord) -> None:
        """Append a new pick. If at capacity, the oldest is dropped (FIFO)."""
        with self._lock:
            self._records.append(record)

    def snapshot(self) -> List[PickRecord]:
        """Return a copy of the current history (oldest first)."""
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        """Drop all records. Used for tests."""
        with self._lock:
            self._records.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


class MetricsCollector:
    """Singleton holder of the pick history + cache reference.

    Wired into the endpoint:
    - pick endpoint calls `record_pick(...)` after computing the winner
    - metrics endpoint calls `current_state(...)` + `pick_history_snapshot()`
    """

    def __init__(self, history: Optional[PickHistory] = None) -> None:
        # Explicit None check — `history or PickHistory()` would ignore an
        # explicitly-passed empty PickHistory (PickHistory instances are
        # always truthy as objects, even when empty). Use a None check so
        # the caller's intent is honored exactly.
        self._history = history if history is not None else PickHistory()

    def record_pick(
        self,
        task: str,
        model: str,
        score: float,
        weights_used: Dict[str, float],
    ) -> None:
        """Record a successful pick. Called by the pick endpoint."""
        self._history.record(
            PickRecord(
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                task=task,
                model=model,
                score=score,
                weights_used=weights_used,
            )
        )

    def pick_history_snapshot(self) -> List[Dict[str, Any]]:
        """Return the current pick history as a list of dicts (oldest first)."""
        return [r.to_dict() for r in self._history.snapshot()]

    def current_state(
        self,
        task_registry: TaskRegistry,
        model_registry: ModelRegistry,
        cache: DailyRefreshCache,
    ) -> Dict[str, Any]:
        """Snapshot of the current per-task state for the metrics endpoint.

        Combines:
        - Cache freshness (last_loaded_at, age_seconds, is_fresh)
        - Per-task weights + candidate count
        - Per-task current pick (top-scoring model) + score

        The "current pick" is computed in-process from the live registries
        (matching what the /pick endpoint would return). This means the
        metrics reflect what the picker WOULD return, not what it DID
        return (use pick_history for that).
        """
        from utils.auto_router.scoring import score  # avoid circular import at module load

        # Cache state
        last_loaded = cache.last_loaded_wall_time()
        age = cache.age_seconds
        is_fresh = cache.has_value and (age is not None and age < cache.ttl_seconds)

        # Per-task state
        tasks: Dict[str, Any] = {}
        for task_spec in task_registry.all():
            cands = model_registry.candidates_for(task_spec.name)
            if cands:
                scored = sorted(
                    ((m, score(m, task_spec)) for m in cands),
                    key=lambda pair: (-pair[1], pair[0].id),
                )
                winner, winner_score = scored[0]
            else:
                winner, winner_score = None, None
            tasks[task_spec.name] = {
                "weights": {
                    "quality": task_spec.quality_weight,
                    "latency": task_spec.latency_weight,
                    "cost": task_spec.cost_weight,
                },
                "candidate_count": len(cands),
                "current_pick": winner.id if winner else None,
                "current_score": winner_score,
            }

        return {
            "cache": {
                "last_loaded_at": (last_loaded.isoformat().replace("+00:00", "Z") if last_loaded is not None else None),
                "age_seconds": age,
                "is_fresh": bool(is_fresh),
            },
            "tasks": tasks,
        }
