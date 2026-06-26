"""Shared helpers for patching the code-defined canonical memory cohort in unit tests."""

from __future__ import annotations

import utils.memory.memory_system as memory_system_mod


def set_canonical_cohort(monkeypatch, *uids: str) -> None:
    """Inject test uids into ``CANONICAL_MEMORY_USERS`` (empty set clears the cohort)."""
    monkeypatch.setattr(memory_system_mod, "CANONICAL_MEMORY_USERS", frozenset(uids))


def clear_canonical_cohort(monkeypatch) -> None:
    """Reset cohort to empty (global legacy kill-switch state)."""
    set_canonical_cohort(monkeypatch)
