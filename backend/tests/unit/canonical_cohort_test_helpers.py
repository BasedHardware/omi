"""Shared helpers for patching the code-defined canonical memory cohort in unit tests."""

from __future__ import annotations

import importlib
import sys


def set_canonical_cohort(monkeypatch, *uids: str) -> None:
    """Inject canonical test uids and matching env activation."""
    memory_system_mod = importlib.import_module("utils.memory.memory_system")
    monkeypatch.setattr(memory_system_mod, "CANONICAL_MEMORY_USERS", frozenset(uids))
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("utils.memory.") and hasattr(module, "resolve_memory_system"):
            monkeypatch.setattr(module, "resolve_memory_system", memory_system_mod.resolve_memory_system)
    if uids:
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", ",".join(uids))
    else:
        monkeypatch.delenv("MEMORY_MODE", raising=False)
        monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


def clear_canonical_cohort(monkeypatch) -> None:
    """Reset cohort to empty (global legacy kill-switch state)."""
    set_canonical_cohort(monkeypatch)
