"""Cascade retraction converges under account-global control CAS races (#11726).

Concurrent same-uid canonical writes — parallel ``DELETE
/v1/conversations/{id}?cascade=true``, extractions, merges — all bump the one
``memory_state/apply_control`` document. ``replace_conversation_sourced_memories``
answers those races with ``ConversationSourceReplacementConflict`` and, after
three immediate attempts, ``RuntimeError`` → unhandled HTTP 500, while the
Flutter client retried the same conversation up to 12× and kept the storm fed.

These tests pin the convergence contract on the retraction entry
(``retract_conversation_sourced_memories``), the only path cascade delete and
merge use:

* injected control-change conflicts are retried with bounded backoff and
  converge instead of raising;
* a source whose retraction was already committed elsewhere — including the
  stale-receipt shape after another conversation's replacement advanced the
  generation — returns the committed-empty result instead of livelocking on
  ``source replacement operation already exists``;
* a source that still has live items after every bounded round keeps raising,
  so the caller fails closed with the conversation and its memories intact
  (the #11627 fence must not regress).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_j_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _cascade_retract_import_isolation():
    saved = snapshot_sys_modules(["database._client", "firebase_admin", "utils.subscription", "database.users"])
    install_database_client_stub()
    install_ws_j_heavy_import_stubs()
    yield
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from database.memory_apply_store import ConversationSourceReplacementConflict  # noqa: E402
from models.memory_apply import MemoryControlState  # noqa: E402
from models.product_memory import MemoryItemStatus  # noqa: E402
from utils.memory.canonical_memory_adapter import ConversationReplacementConflictError  # noqa: E402
from tests.unit.fixtures.canonical_memory_fakes import (  # noqa: E402
    _FakeDb,
    _sample_memory_payload,
    _trusted_account_generation,
)

UID = "uid-cascade-retract"


@pytest.fixture(autouse=True)
def _reset_universal_memory_env(monkeypatch):
    from tests.unit.universal_memory_test_helpers import reset_universal_memory_fixture

    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    globals()["retract_conversation_sourced_memories"] = canonical_adapter.retract_conversation_sourced_memories
    globals()["write_canonical_extraction_memory"] = canonical_adapter.write_canonical_extraction_memory
    monkeypatch.setattr(
        canonical_adapter,
        "read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    reset_universal_memory_fixture(monkeypatch)


def _cascade_db() -> _FakeDb:
    return _FakeDb(
        {
            f"users/{UID}/memory_state/apply_control": MemoryControlState(
                uid=UID,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )


class _ConflictInjector:
    """Wraps the adapter's store boundary with deterministic CAS races.

    Raises ``ConversationSourceReplacementConflict`` — the exact class the
    Firestore transaction fence raises when the account-global control moved —
    for the first ``conflicts`` calls (``None`` = every call), then delegates
    to the real store.
    """

    def __init__(self, conflicts: int | None):
        self.conflicts = conflicts
        self.calls = 0
        canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
        self._real = canonical_adapter.replace_conversation_source_firestore

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.conflicts is None or self.calls <= self.conflicts:
            raise ConversationSourceReplacementConflict("memory control changed during conversation replacement")
        return self._real(*args, **kwargs)


def _write_source_item(db: _FakeDb, conversation_id: str, content: str) -> str:
    payload = _sample_memory_payload(uid=UID, conversation_id=conversation_id, content=content)
    # The shared fixture hardcodes one evidence id; distinct sources need
    # distinct evidence docs or retraction's staleness fence trips on the
    # overwritten peer (ws_j does the same re-keying).
    payload["evidence"][0]["evidence_id"] = f"ev_{conversation_id}"
    write_canonical_extraction_memory(UID, payload, db_client=db)
    return payload["id"]


def _record_retract_backoff(monkeypatch) -> list[float]:
    sleeps: list[float] = []
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    monkeypatch.setattr(canonical_adapter, "time", SimpleNamespace(sleep=sleeps.append))
    return sleeps


def test_injected_control_change_conflicts_converge_instead_of_raising(monkeypatch):
    db = _cascade_db()
    conversation_id = "conv-converge"
    memory_id = _write_source_item(db, conversation_id, "User enjoys hiking")
    sleeps = _record_retract_backoff(monkeypatch)

    injector = _ConflictInjector(conflicts=3)  # one full internal exhaustion round
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.replace_conversation_source_firestore",
        injector,
    )

    result = retract_conversation_sourced_memories(UID, conversation_id, db_client=db)

    assert result["retracted_memory_ids"] == [memory_id]
    assert db.docs[f"users/{UID}/memory_items/{memory_id}"]["status"] == MemoryItemStatus.tombstoned.value
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 2
    assert injector.calls == 4  # 3 conflicted rounds, then the converged commit
    assert sleeps == [0.05]  # bounded backoff between outer rounds only


def test_repeat_retract_with_stale_receipt_returns_already_retracted(monkeypatch):
    db = _cascade_db()
    first_conversation = "conv-retracted-first"
    second_conversation = "conv-retracted-second"
    first_id = _write_source_item(db, first_conversation, "User enjoys hiking")
    second_id = _write_source_item(db, second_conversation, "User keeps a journal")

    assert retract_conversation_sourced_memories(UID, first_conversation, db_client=db)["retracted_memory_ids"] == [
        first_id
    ]
    # Another conversation's replacement advances source_generation, which
    # makes the first conversation's committed receipt stale: the deterministic
    # operation replans and hits "source replacement operation already exists".
    assert retract_conversation_sourced_memories(UID, second_conversation, db_client=db)["retracted_memory_ids"] == [
        second_id
    ]
    control = db.docs[f"users/{UID}/memory_state/apply_control"]
    assert control["source_generation"] == 3

    sleeps = _record_retract_backoff(monkeypatch)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.replace_conversation_source_firestore",
        _ConflictInjector(conflicts=None),  # the CAS never wins again
    )

    result = retract_conversation_sourced_memories(UID, first_conversation, db_client=db)

    assert result["retracted_memory_ids"] == []
    assert result["committed_memory_ids"] == []
    assert result["source_generation"] == 3
    assert sleeps == []  # converged on the post-conflict completion check
    # The peer conversation's retracted state is untouched.
    assert db.docs[f"users/{UID}/memory_items/{second_id}"]["status"] == MemoryItemStatus.tombstoned.value


def test_exhausted_conflicts_with_live_items_fail_closed(monkeypatch):
    db = _cascade_db()
    conversation_id = "conv-live-under-storm"
    memory_id = _write_source_item(db, conversation_id, "User climbs on weekends")
    sleeps = _record_retract_backoff(monkeypatch)

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.replace_conversation_source_firestore",
        _ConflictInjector(conflicts=None),
    )

    with pytest.raises(ConversationReplacementConflictError):
        retract_conversation_sourced_memories(UID, conversation_id, db_client=db)

    # Bounded retry budget: one backoff sleep per non-final outer round.
    assert sleeps == [0.05, 0.1, 0.25, 0.5]
    # Nothing was retracted — the caller must keep the conversation and its
    # live memories intact (#11627 fence).
    assert db.docs[f"users/{UID}/memory_items/{memory_id}"]["status"] == MemoryItemStatus.active.value
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 1
