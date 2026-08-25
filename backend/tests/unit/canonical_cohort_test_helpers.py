"""Shared helpers for patching the code-defined canonical memory cohort in unit tests."""

from __future__ import annotations

import importlib
import sys


def set_canonical_cohort(monkeypatch, *uids: str) -> None:
    """Inject canonical test uids into the one code-owned selector."""
    cohort_config = importlib.import_module("config.canonical_memory_cohort")
    memory_system_mod = importlib.import_module("utils.memory.memory_system")
    monkeypatch.setattr(cohort_config, "CANONICAL_MEMORY_USERS", frozenset(uids))
    monkeypatch.setattr(memory_system_mod, "CANONICAL_MEMORY_USERS", frozenset(uids))

    def _is_canonical_memory_user(uid: object) -> bool:
        return bool(uid) and isinstance(uid, str) and uid in frozenset(uids)

    monkeypatch.setattr(cohort_config, "is_canonical_memory_user", _is_canonical_memory_user)
    for module_name, module in list(sys.modules.items()):
        if hasattr(module, "is_canonical_memory_user"):
            monkeypatch.setattr(module, "is_canonical_memory_user", _is_canonical_memory_user)
        if (module_name.startswith("utils.memory.") or module_name.startswith("utils.task_intelligence.")) and hasattr(
            module, "resolve_memory_system"
        ):
            monkeypatch.setattr(module, "resolve_memory_system", memory_system_mod.resolve_memory_system)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


def clear_canonical_cohort(monkeypatch) -> None:
    """Reset cohort to empty (global legacy kill-switch state)."""
    set_canonical_cohort(monkeypatch)
