"""Conversation memory extraction survives account-global control CAS races.

``replace_conversation_sourced_memories`` is the write boundary every canonical
memory path shares. Retraction wraps it in a converging loop (#11726), but
extraction calls it straight from conversation processing
(``process_conversation -> _extract_memories -> _extract_memories_canonical``),
and that call is intentionally fail-closed: when it raises, the whole
enrichment fails, so the user's conversation gets no memories *and* no summary.

Prod (Cloud Run ``backend``, 2026-08-19) showed the replacement's three
immediate attempts exhausting under sustained same-account contention —
``ConversationSourceReplacementConflict: memory control changed during
conversation replacement`` on four instances at once, bursting at 15:45Z,
17:33Z and 22:55Z. An immediate retry re-reads the control the peer just
advanced, so the writers keep losing in lockstep.

These tests pin the backoff contract on the extraction entry:

* conflicts that outlast the old immediate budget now converge and commit;
* the retry budget stays bounded, and exhausting it still fails closed with the
  account's control and items untouched (the #11627 fence must not regress);
* callers that own an outer converging loop can still ask for immediate rounds.
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
def _replacement_backoff_import_isolation():
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

UID = "uid-replacement-backoff"
CONVERSATION_ID = "conv-extraction-under-storm"


@pytest.fixture(autouse=True)
def _reset_universal_memory_env(monkeypatch):
    from tests.unit.universal_memory_test_helpers import reset_universal_memory_fixture

    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    globals()["replace_conversation_sourced_memories"] = canonical_adapter.replace_conversation_sourced_memories
    monkeypatch.setattr(
        canonical_adapter,
        "read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    reset_universal_memory_fixture(monkeypatch)


def _extraction_db() -> _FakeDb:
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
    """Raises the transaction fence's conflict for the first ``conflicts`` calls.

    ``None`` conflicts on every call, standing in for a storm that never lets up.
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


def _record_backoff(monkeypatch) -> list[float]:
    sleeps: list[float] = []
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    monkeypatch.setattr(canonical_adapter, "time", SimpleNamespace(sleep=sleeps.append))
    return sleeps


def _install_injector(monkeypatch, conflicts: int | None) -> _ConflictInjector:
    injector = _ConflictInjector(conflicts=conflicts)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.replace_conversation_source_firestore",
        injector,
    )
    return injector


def _extracted_items() -> list[dict]:
    return [_sample_memory_payload(uid=UID, conversation_id=CONVERSATION_ID, content="User enjoys hiking")]


def test_extraction_converges_past_the_immediate_retry_budget(monkeypatch):
    db = _extraction_db()
    items = _extracted_items()
    sleeps = _record_backoff(monkeypatch)
    injector = _install_injector(monkeypatch, conflicts=4)  # one more than the old budget allowed

    result = replace_conversation_sourced_memories(UID, CONVERSATION_ID, items, db_client=db)

    assert result["committed_memory_ids"] == [items[0]["id"]]
    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 2
    assert injector.calls == 5  # 4 conflicted rounds, then the commit
    assert sleeps == [0.05, 0.1, 0.25, 0.5]


def test_extraction_retry_budget_stays_bounded_and_fails_closed(monkeypatch):
    db = _extraction_db()
    items = _extracted_items()
    sleeps = _record_backoff(monkeypatch)
    injector = _install_injector(monkeypatch, conflicts=None)

    with pytest.raises(ConversationReplacementConflictError):
        replace_conversation_sourced_memories(UID, CONVERSATION_ID, items, db_client=db)

    assert injector.calls == 5  # one backoff entry per non-final round
    assert sleeps == [0.05, 0.1, 0.25, 0.5]
    # Nothing was committed — the caller keeps failing closed on the #11627 fence.
    assert f"users/{UID}/memory_items/{items[0]['id']}" not in db.docs
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 1


def test_caller_owning_an_outer_loop_keeps_immediate_rounds(monkeypatch):
    db = _extraction_db()
    items = _extracted_items()
    sleeps = _record_backoff(monkeypatch)
    injector = _install_injector(monkeypatch, conflicts=None)

    with pytest.raises(ConversationReplacementConflictError):
        replace_conversation_sourced_memories(
            UID,
            CONVERSATION_ID,
            items,
            db_client=db,
            conflict_backoff_seconds=(0.0, 0.0),
        )

    assert injector.calls == 3
    assert sleeps == []
