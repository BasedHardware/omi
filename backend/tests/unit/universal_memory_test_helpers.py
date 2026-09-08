"""Temporary test helpers while old fixture setup migrates to universal authority."""

from __future__ import annotations


def configure_universal_memory(monkeypatch, *uids: str) -> None:
    """Retain old fixture calls as a no-op; every nonblank UID is canonical."""
    assert all(isinstance(uid, str) and uid.strip() for uid in uids)
    monkeypatch.setenv("MEMORY_MODE", "read")


def reset_universal_memory_fixture(monkeypatch) -> None:
    """Reset obsolete rollout env without changing universal authority."""
    configure_universal_memory(monkeypatch)
