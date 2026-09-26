from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.memory_apply import MemoryControlState, WriterMode
from utils.memory import canonical_memory_adapter as adapter
from utils.memory.knowledge_ledger_writer_transition import WriterAdmissionError


class _ReachedCanonicalBuilder(RuntimeError):
    pass


def _control(mode: WriterMode) -> MemoryControlState:
    transitioning = mode in {
        WriterMode.transitioning_to_ledger,
        WriterMode.transitioning_to_compatibility,
    }
    return MemoryControlState(
        uid="u1",
        head_commit_id="head-1",
        account_generation=1,
        source_generation=2,
        writer_mode=mode,
        writer_epoch=1 if mode != WriterMode.compatibility else 0,
        writer_transition_owner="test-transition" if transitioning else None,
    )


def _item(*, ledger: bool):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return SimpleNamespace(
        updated_at=now,
        captured_at=now,
        ledger_schema_version="knowledge_ledger.v1" if ledger else None,
    )


@pytest.mark.parametrize(
    ("mode", "ledger_payload", "dedicated_authority", "admitted"),
    [
        (WriterMode.compatibility, False, False, True),
        (WriterMode.compatibility, True, True, False),
        (WriterMode.ledger, False, False, False),
        (WriterMode.ledger, True, True, True),
        (WriterMode.transitioning_to_ledger, False, False, False),
        (WriterMode.transitioning_to_ledger, True, True, False),
        (WriterMode.transitioning_to_compatibility, False, False, False),
        (WriterMode.transitioning_to_compatibility, True, True, False),
    ],
)
def test_extraction_boundary_classifies_writer_before_building_patch(
    monkeypatch, mode, ledger_payload, dedicated_authority, admitted
):
    monkeypatch.setattr(adapter, "_ensure_control_state", lambda *_args, **_kwargs: _control(mode))
    monkeypatch.setattr(
        adapter,
        "_canonical_extraction_apply_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_ReachedCanonicalBuilder()),
    )
    payload = {"content": "test"}
    if ledger_payload:
        payload["ledger_schema_version"] = "knowledge_ledger.v1"

    expected = _ReachedCanonicalBuilder if admitted else WriterAdmissionError
    with pytest.raises(expected):
        adapter.write_canonical_extraction_memory(
            "u1",
            payload,
            db_client=object(),
            _ledger_authority=adapter._LEDGER_WRITE_AUTHORITY if dedicated_authority else None,
        )


@pytest.mark.parametrize(
    ("mode", "admitted"),
    [
        (WriterMode.compatibility, True),
        (WriterMode.ledger, True),
        (WriterMode.transitioning_to_ledger, False),
        (WriterMode.transitioning_to_compatibility, False),
    ],
)
def test_explicit_user_ledger_correction_is_available_only_in_stable_modes(monkeypatch, mode, admitted):
    monkeypatch.setattr(adapter, "_ensure_control_state", lambda *_args, **_kwargs: _control(mode))
    monkeypatch.setattr(
        adapter,
        "_canonical_extraction_apply_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_ReachedCanonicalBuilder()),
    )

    expected = _ReachedCanonicalBuilder if admitted else WriterAdmissionError
    with pytest.raises(expected):
        adapter.write_canonical_extraction_memory(
            "u1",
            {"content": "corrected", "ledger_schema_version": "knowledge_ledger.v1"},
            db_client=object(),
            evidence_items=[SimpleNamespace(source_type="explicit_user_correction")],
            _ledger_authority=adapter._LEDGER_WRITE_AUTHORITY,
            _direct_user_authority=adapter._DIRECT_USER_LEDGER_WRITE_AUTHORITY,
        )


@pytest.mark.parametrize(
    ("mode", "ledger_item", "allow_migration", "admitted"),
    [
        (WriterMode.compatibility, False, False, True),
        (WriterMode.compatibility, False, True, True),
        (WriterMode.compatibility, True, False, True),
        (WriterMode.ledger, False, False, True),
        (WriterMode.ledger, True, False, True),
        (WriterMode.transitioning_to_ledger, False, True, True),
        (WriterMode.transitioning_to_ledger, True, False, False),
        (WriterMode.transitioning_to_compatibility, False, True, False),
    ],
)
def test_mutation_boundary_classifies_existing_row_and_migration_capability(
    monkeypatch, mode, ledger_item, allow_migration, admitted
):
    monkeypatch.setattr(adapter, "_read_canonical_memory_item", lambda *_args, **_kwargs: _item(ledger=ledger_item))
    monkeypatch.setattr(adapter, "_ensure_control_state", lambda *_args, **_kwargs: _control(mode))

    def reached_builder(_item, _now):
        raise _ReachedCanonicalBuilder()

    expected = _ReachedCanonicalBuilder if admitted else WriterAdmissionError
    with pytest.raises(expected):
        adapter._apply_canonical_user_mutation(
            "u1",
            "mem-1",
            mutation_kind="admission-test",
            build_patch=reached_builder,
            allow_ledger_migration=allow_migration,
            db_client=object(),
        )


def test_external_create_is_admitted_as_user_writer_in_ledger_mode(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(adapter, "_evidence_items_from_payload", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(adapter, "_reissued_external_evidence", lambda *_args, **_kwargs: [])

    def capture_write(*_args, **kwargs):
        captured.update(kwargs)
        raise _ReachedCanonicalBuilder()

    monkeypatch.setattr(adapter, "write_canonical_extraction_memory", capture_write)
    with pytest.raises(_ReachedCanonicalBuilder):
        adapter.write_canonical_external_memory("u1", {"content": "remember this"}, db_client=object())
    assert captured["_direct_user_authority"] is adapter._DIRECT_USER_LEDGER_WRITE_AUTHORITY
