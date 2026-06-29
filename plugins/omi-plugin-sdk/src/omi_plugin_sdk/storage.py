"""Storage helpers that avoid changing app-specific persisted data shapes."""

from typing import MutableMapping, TypeVar

T = TypeVar("T")


def get_user_record(store: MutableMapping[str, T], uid: str) -> T | None:
    """Read a user-scoped record from an app-owned mapping."""
    return store.get(uid)


def set_user_record(store: MutableMapping[str, T], uid: str, record: T) -> T:
    """Write a user-scoped record to an app-owned mapping."""
    store[uid] = record
    return record
