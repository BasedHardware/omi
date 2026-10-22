"""Recovery CAS and the real controller's refusal/telemetry paths."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import stale_conversation_recovery as recovery
from routers.listen import conversations as live
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.observability.stale_recovery import STALE_RECOVERY_OUTCOME_TOTAL

NOW = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)


def test_page_claim_cas_and_backoff():
    db = StrictFirestore()
    ref = db.collection('users').document('u').collection('conversation_recovery_state').document('stale_in_progress')
    cursor = {'id': 'poison', 'finished_at': NOW - timedelta(days=30)}
    assert recovery._claim_page_txn(db.transaction(), ref, 0, cursor, NOW)
    assert ref.get().to_dict() == {'revision': 1, 'cursor': cursor, 'not_before': NOW + recovery.PAGE_BACKOFF}
    assert not recovery._claim_page_txn(db.transaction(), ref, 0, None, NOW + timedelta(minutes=2))
    assert not recovery._claim_page_txn(db.transaction(), ref, 1, None, NOW + timedelta(seconds=59))
    assert recovery._claim_page_txn(db.transaction(), ref, 1, None, NOW + recovery.PAGE_BACKOFF)
    assert ref.get().to_dict()['cursor'] is None


def host_for(data):
    async def call(fn, *_args, **_kwargs):
        if fn is live.conversations_db.get_conversation:
            return data
        raise AssertionError(f'Unexpected write: {fn.__name__}')

    return SimpleNamespace(
        persistence=SimpleNamespace(call=call),
        request=SimpleNamespace(uid='private-account'),
        state=SimpleNamespace(current_conversation_id=None),
    )


@pytest.mark.parametrize('guard', ['discarded', 'deleted', 'is_locked', 'deferred'])
async def test_protected_row_is_explicit_noop_without_delete(guard, caplog):
    controller = live.LiveConversationController(host_for({'id': 'poison', guard: True}))
    with caplog.at_level('INFO'):
        assert await controller.process_conversation('poison') is False
    assert f'outcome={guard}' in caplog.text
    assert 'private-account' not in caplog.text


async def test_empty_delete_refusal_is_logged(caplog):
    host = host_for({'id': 'lineage', 'sync_content_revision': 1})
    host.recording_session_ids_by_conversation = {}

    async def call(fn, *_args, **_kwargs):
        if fn is live.conversations_db.get_conversation:
            return {'id': 'lineage', 'sync_content_revision': 1}
        if fn is live.lifecycle_service.delete_empty_recording_conversation:
            return False
        raise AssertionError(fn.__name__)

    host.persistence.call = call
    with caplog.at_level('INFO'):
        assert await live.LiveConversationController(host).process_conversation('lineage') is False
    assert 'outcome=empty_delete_refused' in caplog.text


async def test_isolated_false_counts_noop_not_success(caplog):
    controller = live.LiveConversationController(host_for(None))
    before = STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='not_admitted')._value.get()
    with caplog.at_level('INFO'):
        await controller._finalize_isolated(AsyncMock(return_value=False), 'poison', stage='stale_in_progress')
    assert STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='not_admitted')._value.get() == before + 1
    assert 'Listen stale recovery outcome=not_admitted conversation=poison' in caplog.text
    assert 'private-account' not in caplog.text


async def test_kill_switch_prevents_scan_and_claim(monkeypatch):
    monkeypatch.setenv('STALE_IN_PROGRESS_RECOVERY_ENABLED', 'false')
    await live.LiveConversationController(host_for(None)).recover_stale_in_progress()


async def test_scan_failure_does_not_end_socket(caplog):
    async def fail(*_args, **_kwargs):
        raise RuntimeError('sensitive message must not escape')

    host = host_for(None)
    host.persistence.call = fail
    await live.LiveConversationController(host).recover_stale_in_progress()
    assert 'scan failed type=RuntimeError' in caplog.text
    assert 'sensitive' not in caplog.text


async def test_cancelled_attempt_is_not_reported_as_noop():
    controller = live.LiveConversationController(host_for(None))
    before = STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='cancelled')._value.get()
    with pytest.raises(asyncio.CancelledError):
        await controller._finalize_isolated(
            AsyncMock(side_effect=asyncio.CancelledError), 'cancelled', stage='stale_in_progress'
        )
    assert STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='cancelled')._value.get() == before + 1


async def test_noop_route_is_not_reported_as_success(monkeypatch, caplog):
    host = host_for(None)
    host.request_conversation_processing = AsyncMock()
    host.client_kind = 'ios'
    host.persistence.call = AsyncMock(return_value={'route': 'noop', 'status': 'terminal'})
    monkeypatch.setattr(live, 'get_byok_keys', lambda: {})
    with caplog.at_level('INFO'):
        assert await live.LiveConversationController(host).schedule_finalization('poison') is False
    assert 'outcome=terminal' in caplog.text
    host.request_conversation_processing.assert_not_called()


async def test_isolated_success_counts_accepted(caplog):
    controller = live.LiveConversationController(host_for(None))
    before = STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='accepted')._value.get()
    with caplog.at_level('INFO'):
        await controller._finalize_isolated(AsyncMock(return_value=True), 'accepted', stage='stale_in_progress')
    assert STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome='accepted')._value.get() == before + 1
    assert 'Listen stale recovery outcome=accepted conversation=accepted' in caplog.text


async def test_default_on_scans_when_switch_is_unset(monkeypatch):
    monkeypatch.delenv('STALE_IN_PROGRESS_RECOVERY_ENABLED', raising=False)
    host = host_for(None)
    host.persistence.call = AsyncMock(return_value=[])
    await live.LiveConversationController(host).recover_stale_in_progress()
    assert host.persistence.call.await_args.args[0] is recovery.get_stale_recovery_page
