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


def test_conversation_yielding_no_memories_is_a_noop_not_a_deletion(monkeypatch):
    """A conversation that extracts nothing must not enter the deletion boundary.

    Prod regression (2026-08-28 -> 08-30): #12084 began requiring an
    ``explicit_memory_deletion`` gate token for any empty replacement, because
    an empty replacement normally *removes* a conversation's rows. Conversation
    finalization holds no such gate, so a conversation that simply produced no
    memories raised ``LegalHoldAuthorityUnavailable`` and returned 500. It ran
    at a 74% failure rate on ``/v1/conversations/from-segments`` for two days.

    With no extracted items and no prior rows for the conversation, there is
    nothing to write and nothing to retract, so the call must resolve as a
    no-op without reaching the destructive path at all.
    """

    db = _extraction_db()
    injector = _install_injector(monkeypatch, conflicts=0)

    result = replace_conversation_sourced_memories(UID, CONVERSATION_ID, [], db_client=db)

    assert result["committed_memory_ids"] == []
    assert result["retracted_memory_ids"] == []
    assert result["reactivated_memory_ids"] == []
    # The destructive boundary was never reached, so no gate was ever needed.
    assert injector.calls == 0
    # And the account's control state is untouched.
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 1


def test_empty_replacement_over_existing_rows_still_demands_the_gate(monkeypatch):
    """The compliance rule itself must survive the no-op shortcut.

    This is the other half of the fix: emptying a conversation that *does* have
    canonical rows genuinely retracts them, so it must still be refused without
    ``explicit_memory_deletion`` authority. Only the provably-nothing-to-do case
    returns early.
    """

    from database.legal_holds import LegalHoldAuthorityUnavailable

    db = _extraction_db()
    items = _extracted_items()
    replace_conversation_sourced_memories(UID, CONVERSATION_ID, items, db_client=db)
    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value

    # Same conversation, now extracting nothing: this removes the row above.
    with pytest.raises(LegalHoldAuthorityUnavailable):
        replace_conversation_sourced_memories(UID, CONVERSATION_ID, [], db_client=db)

    # Fail-closed: the row survives the refused deletion.
    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value


def test_extraction_intent_empty_over_existing_rows_is_a_noop_that_keeps_them(monkeypatch):
    """Reprocess extracting nothing must keep the rows, not 500 or delete them.

    Residual prod regression after #12410: conversation *reprocess*
    (``routers/conversations.py -> process_conversation``) over a conversation
    that already has canonical rows, where the new extraction is empty. The
    empty replacement genuinely would retract rows, so it kept demanding the
    ``explicit_memory_deletion`` gate the extraction path never holds and died
    with LegalHoldAuthorityUnavailable. Extraction emptiness is model variance,
    not deletion intent (FC-destructive-gate-keyed-on-proxy-for-intent), so the
    extraction caller now declares its intent and the existing rows survive as
    a successful no-op.
    """

    db = _extraction_db()
    items = _extracted_items()
    replace_conversation_sourced_memories(UID, CONVERSATION_ID, items, db_client=db)
    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value
    injector = _install_injector(monkeypatch, conflicts=0)

    result = replace_conversation_sourced_memories(
        UID,
        CONVERSATION_ID,
        [],
        db_client=db,
        empty_set_intent="extraction",
    )

    assert result["retracted_memory_ids"] == []
    assert result["committed_memory_ids"] == []
    assert result["reactivated_memory_ids"] == []
    # The rows survive and the destructive boundary was never entered.
    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value
    assert injector.calls == 0
    assert db.docs[f"users/{UID}/memory_state/apply_control"]["source_generation"] == 2


def test_default_intent_still_treats_empty_over_existing_rows_as_a_retraction():
    """The extraction shortcut must not relax the deletion callers' contract."""

    from database.legal_holds import LegalHoldAuthorityUnavailable

    db = _extraction_db()
    items = _extracted_items()
    replace_conversation_sourced_memories(UID, CONVERSATION_ID, items, db_client=db)

    with pytest.raises(LegalHoldAuthorityUnavailable):
        replace_conversation_sourced_memories(UID, CONVERSATION_ID, [], db_client=db)

    assert db.docs[f"users/{UID}/memory_items/{items[0]['id']}"]["status"] == MemoryItemStatus.active.value


def test_unknown_empty_set_intent_is_rejected():
    with pytest.raises(ValueError, match="empty_set_intent"):
        replace_conversation_sourced_memories(
            UID, CONVERSATION_ID, [], db_client=_extraction_db(), empty_set_intent="oops"
        )
