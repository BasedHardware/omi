from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import Response

from models.memories import MemoryCategory, MemoryDB
from models.product_memory import LedgerWriteReason, MemoryKind, MemorySubjectScope
from routers import jit_ledger_snapshot as snapshot
from utils.jit_rollout import JITDecisionReason, JITErrorClass, JITRolloutDecision, TriState

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def row(memory_id: str, **updates) -> MemoryDB:
    data = {
        "id": memory_id,
        "uid": "u1",
        "content": "Brooklyn",
        "category": MemoryCategory.manual,
        "tags": [],
        "created_at": NOW,
        "updated_at": NOW,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "subject_scope": MemorySubjectScope.primary_user,
        "slot": "home_city",
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
        "valid_at": NOW,
    }
    data.update(updates)
    return MemoryDB(**data)


def completion():
    return SimpleNamespace(source_head_commit_id="commit-7")


def receipt(rows=()):
    return SimpleNamespace(source_head_commit_id="commit-7", rows=list(rows))


def test_empty_migrated_snapshot_is_authoritatively_enabled(monkeypatch):
    monkeypatch.setattr(snapshot, "read_ledger_migration_completion", lambda *_args, **_kwargs: completion())
    monkeypatch.setattr(snapshot, "read_ledger_prompt_projection_receipt", lambda *_args, **_kwargs: receipt())

    result = snapshot._build_enabled_snapshot("u1", db_client=object())

    assert result.mode == snapshot.LedgerPromptSnapshotMode.enabled
    assert result.rows == []
    assert result.source_head_commit_id == "commit-7"


def test_partial_migration_and_legacy_survivor_receipt_fail_to_compatibility(monkeypatch):
    monkeypatch.setattr(snapshot, "read_ledger_migration_completion", lambda *_args, **_kwargs: None)
    assert snapshot._build_enabled_snapshot("u1", db_client=object()).reason == "migration_incomplete"

    monkeypatch.setattr(snapshot, "read_ledger_migration_completion", lambda *_args, **_kwargs: completion())
    monkeypatch.setattr(snapshot, "read_ledger_prompt_projection_receipt", lambda *_args, **_kwargs: None)
    result = snapshot._build_enabled_snapshot("u1", db_client=object())
    assert result.mode == snapshot.LedgerPromptSnapshotMode.compatibility
    assert result.reason == "projection_receipt_stale"
    assert result.rows == []


def test_receipt_returns_only_its_bounded_projection_without_export_scan(monkeypatch):
    playbook = row(
        "playbook",
        kind=MemoryKind.document,
        slot=None,
        content="Release safely",
        write_reason=LedgerWriteReason.recurring_workflow,
    )
    trigger = row(
        "trigger",
        kind=MemoryKind.trigger,
        slot=None,
        trigger_condition={"keywords": ["release"]},
        write_reason=LedgerWriteReason.standing_trigger,
    )
    monkeypatch.setattr(snapshot, "read_ledger_migration_completion", lambda *_args, **_kwargs: completion())
    monkeypatch.setattr(
        snapshot,
        "read_ledger_prompt_projection_receipt",
        lambda *_args, **_kwargs: receipt([row("profile"), playbook, trigger]),
    )

    result = snapshot._build_enabled_snapshot("u1", db_client=object())

    assert [item.id for item in result.rows] == ["profile", "playbook", "trigger"]


@pytest.mark.parametrize(
    ("rollout", "kill", "effective", "expected"),
    [
        (TriState.ENABLED, TriState.ENABLED, TriState.DISABLED, "killed"),
        (TriState.DISABLED, TriState.DISABLED, TriState.DISABLED, "disabled"),
        (TriState.UNKNOWN, TriState.UNKNOWN, TriState.UNKNOWN, "unknown"),
    ],
)
def test_shared_rollout_and_kill_decision_map_fail_closed(rollout, kill, effective, expected):
    result = snapshot._disabled_snapshot(
        JITRolloutDecision(
            rollout=rollout,
            kill_switch=kill,
            effective=effective,
            reason=JITDecisionReason.EVALUATED,
            error_class=JITErrorClass.NONE,
            cache_hit=False,
            cache_ttl_seconds=0,
        )
    )
    assert result.mode.value == expected
    assert result.rows == []


def decision(*, enabled: bool, killed: bool = False) -> JITRolloutDecision:
    return JITRolloutDecision(
        rollout=TriState.ENABLED if enabled else TriState.DISABLED,
        kill_switch=TriState.ENABLED if killed else TriState.DISABLED,
        effective=TriState.ENABLED if enabled and not killed else TriState.DISABLED,
        reason=JITDecisionReason.EVALUATED,
        error_class=JITErrorClass.NONE,
        cache_hit=False,
        cache_ttl_seconds=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final_decision", "expected_mode"),
    [(decision(enabled=False), "disabled"), (decision(enabled=True, killed=True), "killed")],
)
async def test_flag_or_kill_flip_during_receipt_read_revokes_enabled_snapshot(
    monkeypatch, final_decision, expected_mode
):
    decisions = iter([decision(enabled=True), final_decision])

    async def resolve(*_args, **kwargs):
        current = next(decisions)
        if kwargs.get("force_refresh"):
            assert current is final_decision
        return current

    async def run_in_executor(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(snapshot, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(snapshot, "get_data_plane_firestore_client", lambda: object())
    monkeypatch.setattr(snapshot, "run_blocking", run_in_executor)
    monkeypatch.setattr(
        snapshot,
        "_build_enabled_snapshot",
        lambda *_args, **_kwargs: snapshot.LedgerPromptSnapshotEnvelope(
            mode="enabled", reason="migration_complete_zero_legacy", source_head_commit_id="head-7", rows=[]
        ),
    )

    result = await snapshot.get_knowledge_ledger_prompt_snapshot(response=Response(), uid="u1")
    assert result.mode.value == expected_mode
    assert result.rows == []


@pytest.mark.asyncio
async def test_sync_firestore_client_is_acquired_inside_blocking_boundary(monkeypatch):
    events: list[str] = []

    async def resolve(*_args, **_kwargs):
        return decision(enabled=True)

    async def run_in_executor(_executor, function, *args, **kwargs):
        events.append("blocking-enter")
        result = function(*args, **kwargs)
        events.append("blocking-exit")
        return result

    def firestore_client():
        events.append("firestore-client")
        return object()

    monkeypatch.setattr(snapshot, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(snapshot, "run_blocking", run_in_executor)
    monkeypatch.setattr(snapshot, "get_data_plane_firestore_client", firestore_client)
    monkeypatch.setattr(
        snapshot,
        "_build_enabled_snapshot",
        lambda *_args, **_kwargs: snapshot.LedgerPromptSnapshotEnvelope(
            mode="enabled", reason="migration_complete_zero_legacy", source_head_commit_id="head-7", rows=[]
        ),
    )

    result = await snapshot.get_knowledge_ledger_prompt_snapshot(response=Response(), uid="u1")

    assert result.mode == snapshot.LedgerPromptSnapshotMode.enabled
    assert events == ["blocking-enter", "firestore-client", "blocking-exit"]
