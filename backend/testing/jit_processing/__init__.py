"""Fixture-backed, deterministic contracts for JIT processing evaluation."""

from .save_policy import (
    JITSaveDecision,
    evaluate_fixture_case,
    evaluate_save_candidate,
    load_fixture_cases,
)

__all__ = [
    "JITSaveDecision",
    "evaluate_fixture_case",
    "evaluate_save_candidate",
    "load_fixture_cases",
]
