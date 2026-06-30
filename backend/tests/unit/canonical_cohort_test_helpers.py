"""Shared helpers for patching the code-defined canonical memory cohort in unit tests."""

from __future__ import annotations

import utils.memory.memory_system as memory_system_mod


def set_canonical_cohort(monkeypatch, *uids: str) -> None:
    """Inject canonical test uids and matching env activation."""
    monkeypatch.setattr(memory_system_mod, "CANONICAL_MEMORY_USERS", frozenset(uids))
    if uids:
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", ",".join(uids))
    else:
        monkeypatch.delenv("MEMORY_MODE", raising=False)
        monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


def clear_canonical_cohort(monkeypatch) -> None:
    """Reset cohort to empty (global legacy kill-switch state)."""
    set_canonical_cohort(monkeypatch)
