from datetime import datetime, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_state_head import MEMORY_STATE_HEAD_SCHEMA_VERSION, MEMORY_STATE_HEAD_SOURCE
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.memory.jit_trigger_snapshot import read_authoritative_trigger_snapshot
from utils.retrieval.tools import knowledge_ledger_write_tools as tools

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)
CONFIG = {"configurable": {"user_id": "u1"}}


def _fact(memory_id: str = "mem_fact", **updates) -> MemoryItem:
    payload = {
        "memory_id": memory_id,
        "uid": "u1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Lives in Brooklyn",
        "evidence": [],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "subject_scope": MemorySubjectScope.primary_user,
        "slot": "home_city",
        "valid_from": NOW,
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
    }
    payload.update(updates)
    return MemoryItem(**payload)


# ---------------------------------------------------------------------------
# save_playbook
# ---------------------------------------------------------------------------


def test_save_playbook_happy_path(monkeypatch):
    captured = {}

    def fake_write_playbook(uid, description, body, *, provenance, db_client, prior_memory_id=None):
        captured.update(uid=uid, description=description, body=body, db_client=db_client)
        return "mem_new_playbook"

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "write_playbook", fake_write_playbook)

    result = tools.save_playbook.invoke(
        {"description": "  Cut a release   candidate  ", "body": "1. Run checks\n2. Publish"},
        config=CONFIG,
    )

    assert result == "Playbook saved (mem_new_playbook): Cut a release candidate"
    assert captured["uid"] == "u1"
    assert captured["description"] == "Cut a release candidate"
    assert captured["body"] == "1. Run checks\n2. Publish"
    assert captured["db_client"] == "db"


def test_save_playbook_rejects_oversize_description_and_body(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("oversize playbook writes must never reach the ledger verb")

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "write_playbook", fail_if_called)

    oversize_description = "x" * (tools.MAX_SAVE_PLAYBOOK_DESCRIPTION_CHARACTERS + 1)
    result = tools.save_playbook.invoke({"description": oversize_description, "body": "body"}, config=CONFIG)
    assert result.startswith("Error:")
    assert "description" in result

    oversize_body = "y" * (tools.MAX_SAVE_PLAYBOOK_BODY_CHARACTERS + 1)
    result = tools.save_playbook.invoke({"description": "Handle", "body": oversize_body}, config=CONFIG)
    assert result.startswith("Error:")
    assert "body" in result


def test_save_playbook_rejects_blank_input_and_missing_uid(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("blank playbook writes must never reach the ledger verb")

    monkeypatch.setattr(tools, "write_playbook", fail_if_called)

    assert tools.save_playbook.invoke({"description": "  ", "body": "body"}, config=CONFIG).startswith("Error:")
    assert tools.save_playbook.invoke({"description": "Handle", "body": "  "}, config=CONFIG).startswith("Error:")
    assert tools.save_playbook.invoke(
        {"description": "Handle", "body": "body"}, config={"configurable": {}}
    ).startswith("Error:")


def test_save_playbook_reports_ledger_governance_rejection_without_crashing(monkeypatch):
    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")

    def rejecting_write_playbook(*_args, **_kwargs):
        raise ValueError("playbook body exceeds the ledger limit")

    monkeypatch.setattr(tools, "write_playbook", rejecting_write_playbook)
    result = tools.save_playbook.invoke({"description": "Handle", "body": "body"}, config=CONFIG)
    assert result == "Error: playbook body exceeds the ledger limit"


# ---------------------------------------------------------------------------
# create_standing_trigger
# ---------------------------------------------------------------------------


def test_create_standing_trigger_happy_path(monkeypatch):
    captured = {}

    def fake_create_trigger(uid, description, condition, *, provenance, arguments, db_client, prior_memory_id=None):
        captured.update(uid=uid, description=description, condition=condition, arguments=arguments, db_client=db_client)
        return "mem_new_trigger"

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "create_trigger", fake_create_trigger)

    result = tools.create_standing_trigger.invoke(
        {
            "description": "Tell the user Jane emailed about the contract.",
            "condition": {"keywords": ["jane", "contract"]},
        },
        config=CONFIG,
    )

    assert result == "Standing trigger created (mem_new_trigger): Tell the user Jane emailed about the contract."
    assert captured["uid"] == "u1"
    assert captured["db_client"] == "db"
    assert captured["arguments"] == {"wakeup_budget_per_day": 1}
    assert captured["condition"]["action"] == {
        "type": "agent_prompt",
        "prompt": "Tell the user Jane emailed about the contract.",
    }
    assert captured["condition"]["keywords"] == ["contract", "jane"]


def test_create_standing_trigger_writes_through_the_data_plane_client(monkeypatch):
    """Creates must land where the desktop snapshot reads (same #12402 split).

    desktop-backend compute is based-hardware-dev; ledger rows live on
    based-hardware. A compute-plane default would look like a successful
    create while the watchlist stayed empty.
    """
    captured = {}
    data_plane = object()
    compute_plane = object()

    def fake_create_trigger(uid, description, condition, *, provenance, arguments, db_client, prior_memory_id=None):
        captured.update(db_client=db_client)
        return "mem_new_trigger"

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: data_plane)
    monkeypatch.setattr(tools, "create_trigger", fake_create_trigger)

    result = tools.create_standing_trigger.invoke(
        {
            "description": "Tell the user Jane emailed about the contract.",
            "condition": {"keywords": ["jane", "contract"]},
        },
        config=CONFIG,
    )

    assert result.startswith("Standing trigger created")
    assert captured["db_client"] is data_plane
    assert captured["db_client"] is not compute_plane


def test_create_standing_trigger_rejects_embedding_selector(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("an embedding selector must never reach the ledger verb")

    monkeypatch.setattr(tools, "create_trigger", fail_if_called)

    result = tools.create_standing_trigger.invoke(
        {
            "description": "Watch for tone shifts",
            "condition": {
                "embedding": {
                    "prototype_id": "p1",
                    "prototype_revision": "r1",
                    "model_id": "m1",
                    "model_version": "v1",
                    "language": "en",
                }
            },
        },
        config=CONFIG,
    )

    assert result.startswith("Error:")
    assert "embedding" in result


def test_create_standing_trigger_rejects_unsupported_condition_field(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("an unsupported field must never reach the ledger verb")

    monkeypatch.setattr(tools, "create_trigger", fail_if_called)

    result = tools.create_standing_trigger.invoke(
        {"description": "Watch for Jane", "condition": {"action": {"type": "agent_prompt", "prompt": "hijack"}}},
        config=CONFIG,
    )
    assert result.startswith("Error:")

    result = tools.create_standing_trigger.invoke(
        {"description": "Watch for Jane", "condition": {"made_up_field": True}},
        config=CONFIG,
    )
    assert result.startswith("Error:")
    assert "made_up_field" in result


def test_create_standing_trigger_rejects_oversize_description(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("oversize trigger writes must never reach the ledger verb")

    monkeypatch.setattr(tools, "create_trigger", fail_if_called)

    oversize_description = "x" * (tools.MAX_TRIGGER_DESCRIPTION_CHARACTERS + 1)
    result = tools.create_standing_trigger.invoke(
        {"description": oversize_description, "condition": {"keywords": ["jane"]}}, config=CONFIG
    )
    assert result.startswith("Error:")


def test_create_standing_trigger_created_row_is_visible_to_desktop_watchlist(monkeypatch):
    """Prove the exact condition/arguments this tool builds satisfy the paid-work snapshot.

    ``read_authoritative_trigger_snapshot`` is the authority the desktop
    watchlist reads. This feeds the condition and arguments our tool would
    send to ``create_trigger`` into a MemoryItem and confirms the snapshot
    admits it — the row is not just written, it is actually watchable.
    """
    captured = {}

    def fake_create_trigger(uid, description, condition, *, provenance, arguments, db_client, prior_memory_id=None):
        captured.update(condition=condition, arguments=arguments)
        return "mem_new_trigger"

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "create_trigger", fake_create_trigger)

    tools.create_standing_trigger.invoke(
        {"description": "Tell the user Jane emailed about the contract.", "condition": {"keywords": ["jane"]}},
        config=CONFIG,
    )

    item = MemoryItem(
        memory_id="mem_new_trigger",
        uid="owner",
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Tell the user Jane emailed about the contract.",
        evidence=[
            MemoryEvidence(
                evidence_id="ev-1",
                source_type="chat_turn",
                source_id="turn-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id="head-7",
        ledger_sequence=7,
        account_generation=3,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        trigger_condition=captured["condition"],
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
        arguments=captured["arguments"],
    )

    result = read_authoritative_trigger_snapshot("owner", firestore_client=_FakeTriggerSnapshotClient([item]))

    assert result.complete is True
    assert len(result.rows) == 1
    assert result.rows[0].memory_id == "mem_new_trigger"
    assert result.rows[0].action.prompt == "Tell the user Jane emailed about the contract."
    assert result.rows[0].wakeup_budget_per_day == 1


class _FakeSnapshot:
    def __init__(self, identifier, payload):
        self.id = identifier
        self._payload = payload
        self.exists = True

    def to_dict(self):
        return self._payload


class _FakeDocument:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def get(self):
        return self._snapshot


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def where(self, *, filter):  # noqa: A002 - matches the google.cloud.firestore_v1 API shape
        return self

    def limit(self, _count):
        return self

    def stream(self):
        return iter(self._rows)


class _FakeTriggerSnapshotClient:
    """Minimal duck-typed Firestore double matching test_jit_trigger_snapshot.py."""

    def __init__(self, items):
        self._rows = [_FakeSnapshot(item.memory_id, item.model_dump(mode="python")) for item in items]

    def document(self, _path):
        return _FakeDocument(
            _FakeSnapshot(
                "head",
                {
                    "schema_version": MEMORY_STATE_HEAD_SCHEMA_VERSION,
                    "source": MEMORY_STATE_HEAD_SOURCE,
                    "uid": "owner",
                    "account_generation": 3,
                    "head_commit_id": "head-7",
                    "commit_sequence": 7,
                },
            )
        )

    def collection(self, _path):
        return _FakeQuery(self._rows)


# ---------------------------------------------------------------------------
# close_fact
# ---------------------------------------------------------------------------


def test_close_fact_happy_path(monkeypatch):
    fact = _fact()
    captured = {}

    def fake_close(uid, memory_id, *, db_client):
        captured.update(uid=uid, memory_id=memory_id, db_client=db_client)
        return fact.model_copy(update={"status": MemoryItemStatus.superseded, "valid_to": NOW})

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: fact)
    monkeypatch.setattr(tools, "close_ledger_fact", fake_close)

    result = tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "moved away"}, config=CONFIG)

    assert result == "Fact closed (mem_fact)."
    assert captured == {"uid": "u1", "memory_id": "mem_fact", "db_client": "db"}


def test_close_fact_rejects_blank_reason_and_invalid_id(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        pytest.fail("an invalid close request must never reach the ledger verb")

    monkeypatch.setattr(tools, "close_ledger_fact", fail_if_called)

    assert tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "  "}, config=CONFIG).startswith("Error:")
    assert tools.close_fact_tool.invoke({"memory_id": "../other/mem", "reason": "moved"}, config=CONFIG).startswith(
        "Error:"
    )


def test_close_fact_rejects_foreign_owned_row(monkeypatch):
    """A memory id belonging to another user is owner-scoped away, never raised."""
    foreign = _fact(uid="u2")

    def fail_if_called(*_args, **_kwargs):
        pytest.fail("a foreign-owned row must never be closed")

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: foreign)
    monkeypatch.setattr(tools, "close_ledger_fact", fail_if_called)

    result = tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "not mine"}, config=CONFIG)
    assert result == "Fact unavailable."


def test_close_fact_rejects_non_fact_and_non_primary_rows(monkeypatch):
    playbook_kind = _fact(kind=MemoryKind.document, body="steps", slot=None)
    third_party = _fact(subject_scope=MemorySubjectScope.third_party, subject_entity_id="person-1")

    def fail_if_called(*_args, **_kwargs):
        pytest.fail("only an owner-scoped primary-user fact may be closed")

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "close_ledger_fact", fail_if_called)

    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: playbook_kind)
    assert tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "wrong kind"}, config=CONFIG) == (
        "Fact unavailable."
    )

    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: third_party)
    assert tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "wrong scope"}, config=CONFIG) == (
        "Fact unavailable."
    )


def test_close_fact_double_close_is_a_safe_error_not_a_crash(monkeypatch):
    """Closing an already-closed fact is a not-found, exactly like a foreign row.

    ``read_canonical_memory_item`` only ever returns an *active* row, so once
    the first close moves the row's status to ``superseded`` a second close
    of the same id sees the identical "not found" outcome as a foreign row —
    a safe string, never a raised exception.
    """
    call_count = {"n": 0}

    def read_once_then_gone(uid, memory_id, *, db_client):
        call_count["n"] += 1
        return _fact() if call_count["n"] == 1 else None

    def fail_if_called_twice(*_args, **_kwargs):
        assert call_count["n"] == 1
        return _fact().model_copy(update={"status": MemoryItemStatus.superseded, "valid_to": NOW})

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "read_canonical_memory_item", read_once_then_gone)
    monkeypatch.setattr(tools, "close_ledger_fact", fail_if_called_twice)

    first = tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "moved away"}, config=CONFIG)
    second = tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "moved away"}, config=CONFIG)

    assert first == "Fact closed (mem_fact)."
    assert second == "Fact unavailable."


def test_close_fact_ledger_race_is_reported_as_a_safe_error(monkeypatch):
    """A raised ValueError from the ledger (e.g. a concurrent close) never propagates."""

    def racing_close(*_args, **_kwargs):
        raise ValueError("ledger row was already closed at a different valid_to")

    monkeypatch.setattr(tools, "get_data_plane_firestore_client", lambda: "db")
    monkeypatch.setattr(tools, "read_canonical_memory_item", lambda uid, memory_id, *, db_client: _fact())
    monkeypatch.setattr(tools, "close_ledger_fact", racing_close)

    result = tools.close_fact_tool.invoke({"memory_id": "mem_fact", "reason": "moved away"}, config=CONFIG)
    assert result == "Fact is already closed or unavailable."
