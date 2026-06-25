#!/usr/bin/env python3
"""Auto-router v1 demo: show how different per-task weights change the pick.

Run: cd backend && PYENV_VERSION=3.12.8 python -m utils.auto_router.demo.run

Demonstrates 3 scenarios from the user's brief:
  1. Low-cost mode for general assistant → picks cheap model
  2. High-quality mode for screenshot understanding → picks strong model
  3. Low-latency mode for PTT → picks fast model

Each scenario:
  - Shows the original weights for the task
  - Overrides weights to bias toward the named dimension
  - Re-scores all candidates
  - Prints the top 3 picks (so you can see the scoring change, not just the winner)
  - Shows the winner's score delta vs the original-weight winner (if different)

This script does NOT call the HTTP endpoint — it uses the scoring function
directly with overridden weights. Use it to validate the framework's
behavior under different weight scenarios.
"""

import sys
from pathlib import Path

# Path setup so the script runs from anywhere (no install needed).
# File layout: <repo>/backend/utils/auto_router/demo/run.py
#            → parents[3] = backend/, parents[4] = repo root.
_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from utils.auto_router.model_registry import ModelRegistry  # noqa: E402
from utils.auto_router.scoring import score  # noqa: E402
from utils.auto_router.task_registry import TaskRegistry  # noqa: E402

BENCHMARKS = _BACKEND / "utils" / "auto_router" / "benchmarks.example.json"


def load_registries():
    tasks = TaskRegistry.from_json(BENCHMARKS)
    models = ModelRegistry.from_json(BENCHMARKS)
    return tasks, models


def print_section(title: str):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def print_weights(weights: dict):
    print(f"  quality_weight = {weights['quality']}")
    print(f"  latency_weight = {weights['latency']}")
    print(f"  cost_weight    = {weights['cost']}")


def show_picks(
    task_name: str,
    original_weights: dict,
    overridden_weights: dict,
    tasks: TaskRegistry,
    models: ModelRegistry,
):
    print(f"\nTask: {task_name}")
    print(f"\n  Original weights (from benchmarks.example.json):")
    print_weights(original_weights)

    print(f"\n  Override weights (for this demo):")
    print_weights(overridden_weights)

    # Build TaskSpec with original weights
    original_spec = tasks.get(task_name)
    candidates = models.candidates_for(task_name)

    # Score with original
    print(f"\n  Picks with ORIGINAL weights:")
    original_scored = [(m, score(m, original_spec)) for m in candidates]
    original_scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    for i, (m, s) in enumerate(original_scored[:3], 1):
        print(f"    {i}. {m.id:35s} score={s:.4f}  (provider={m.provider})")
    original_winner = original_scored[0]

    # Score with overridden
    overridden_spec = type(original_spec)(
        name=original_spec.name,
        quality_weight=overridden_weights["quality"],
        latency_weight=overridden_weights["latency"],
        cost_weight=overridden_weights["cost"],
        description=original_spec.description,
    )
    print(f"\n  Picks with OVERRIDDEN weights:")
    overridden_scored = [(m, score(m, overridden_spec)) for m in candidates]
    overridden_scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    for i, (m, s) in enumerate(overridden_scored[:3], 1):
        print(f"    {i}. {m.id:35s} score={s:.4f}  (provider={m.provider})")
    overridden_winner = overridden_scored[0]

    if original_winner[0].id == overridden_winner[0].id:
        print(f"\n  → Same winner: {overridden_winner[0].id}")
        print(
            f"    Score change: {original_winner[1]:.4f} → {overridden_winner[1]:.4f} (Δ {overridden_winner[1] - original_winner[1]:+.4f})"
        )
    else:
        print(f"\n  → Winner CHANGED:")
        print(f"    Before: {original_winner[0].id} (score {original_winner[1]:.4f})")
        print(f"    After:  {overridden_winner[0].id} (score {overridden_winner[1]:.4f})")


def main():
    tasks, models = load_registries()

    # Read the ORIGINAL weights from the registry (so the demo output reflects
    # what benchmarks.example.json actually contains — if the JSON changes,
    # the demo output updates automatically instead of going stale).
    def weights_for(task_name: str) -> dict:
        spec = tasks.get(task_name)
        return {
            "quality": spec.quality_weight,
            "latency": spec.latency_weight,
            "cost": spec.cost_weight,
        }

    # Demo 1: Low-cost mode for general_assistant
    print_section("Demo 1: Low-cost mode for general_assistant")
    print("Expected: cheap model wins (cost_weight dominates).")
    show_picks(
        task_name="general_assistant",
        original_weights=weights_for("general_assistant"),
        overridden_weights={"quality": 0.1, "latency": 0.1, "cost": 0.8},
        tasks=tasks,
        models=models,
    )

    # Demo 2: High-quality mode for screenshot_understanding
    print_section("Demo 2: High-quality mode for screenshot_understanding")
    print("Expected: strongest (highest quality_score) model wins.")
    show_picks(
        task_name="screenshot_understanding",
        original_weights=weights_for("screenshot_understanding"),
        overridden_weights={"quality": 0.95, "latency": 0.025, "cost": 0.025},
        tasks=tasks,
        models=models,
    )

    # Demo 3: Low-latency mode for PTT
    print_section("Demo 3: Low-latency mode for ptt_response")
    print("Expected: fastest (highest latency_score) model wins.")
    show_picks(
        task_name="ptt_response",
        original_weights=weights_for("ptt_response"),
        overridden_weights={"quality": 0.05, "latency": 0.9, "cost": 0.05},
        tasks=tasks,
        models=models,
    )

    print()
    print("=" * 70)
    print("All 3 demos complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
