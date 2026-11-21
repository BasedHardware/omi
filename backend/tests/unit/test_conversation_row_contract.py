"""Stored conversation rows: producers fail at the write seam, list reads isolate one malformed row.

Synthetic data only.
"""

import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as db, conversations_v3 as store, conversations_v3_leases as leases
from database.fsr_cache_telemetry import OMI_FALLBACK_TOTAL
from models.conversation import Conversation
from routers import conversations as routes
from utils.conversations import row_contract
from tests.unit.test_conversations_v3_transactions import AT, R, strict  # noqa: F401

C = ('users', 'synthetic', 'conversations', 'c')
SECRET = 'a private remark the log must never carry'


def _row(cid='c', **updates):
    return {
        'id': cid,
        'status': 'completed',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=20),
        'structured': {'title': cid, 'overview': SECRET},
        **updates,
    }


def _broken(cid='bad'):
    # A participant source the reader model rejects (the 2026-11-17 producer-bug class).
    return _row(cid, structured={'title': SECRET, 'participants': [{'name': SECRET, 'source': 'calendar'}]})


def _rejections(producer, outcome):
    return row_contract.WRITE_REJECTIONS.labels(producer=producer, outcome=outcome)._value.get()


def _skips():
    return OMI_FALLBACK_TOTAL.labels(
        component='conversation_row_contract',
        from_mode='strict',
        to_mode='row_skipped',
        reason='malformed_doc',
        outcome='degraded',
    )._value.get()


def test_valid_row_passes_the_write_seam():
    row_contract.check_write(_row(), producer='unit')


def test_invalid_row_fails_at_the_writer_naming_the_producer_without_values(caplog, monkeypatch):
    monkeypatch.delenv(row_contract.WRITE_VALIDATION_ENV, raising=False)
    before = _rejections('unit', 'rejected')
    with caplog.at_level(logging.ERROR, logger=row_contract.__name__):
        with pytest.raises(row_contract.InvalidConversationRow) as raised:
            row_contract.check_write(_broken(), producer='unit')
    assert (raised.value.producer, raised.value.conversation_id) == ('unit', 'bad')
    assert raised.value.paths == ['structured.participants.0.source:literal_error']
    assert _rejections('unit', 'rejected') == before + 1
    assert 'producer=unit' in caplog.text and 'conversation_id=bad' in caplog.text
    assert SECRET not in caplog.text and SECRET not in str(raised.value)


def test_kill_switch_off_logs_and_lets_the_write_through(monkeypatch):
    monkeypatch.setenv(row_contract.WRITE_VALIDATION_ENV, 'false')
    before = _rejections('unit', 'logged')
    row_contract.check_write(_broken(), producer='unit')
    assert _rejections('unit', 'logged') == before + 1


def test_v3_commit_parks_an_invalid_planned_row_and_writes_nothing(strict, monkeypatch):
    monkeypatch.delenv(row_contract.WRITE_VALIDATION_ENV, raising=False)
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    source = {'id': 'r', 'recording': True, '_v3_revision': 1}
    before = _rejections('v3_planner', 'rejected')
    with pytest.raises(store.Conflict, match='invalid_row'):
        store.commit_projection(
            'synthetic', token, {'r': source}, {}, [_broken('c'), _row('c2')], [], firestore_client=strict
        )
    # Nothing committed, the source stays owed, and the counter names the producer.
    assert C not in strict.rows and ('users', 'synthetic', 'conversations', 'c2') not in strict.rows
    assert strict.rows[R]['v3_pending'] is True and 'claims' not in strict.rows[R]
    assert _rejections('v3_planner', 'rejected') == before + 1


def test_v3_commit_with_the_kill_switch_off_commits_as_before(strict, monkeypatch):
    monkeypatch.setenv(row_contract.WRITE_VALIDATION_ENV, 'false')
    strict.rows[R] = {'recording': True, 'v3_pending': True}
    token = leases.acquire('synthetic', 'builder', firestore_client=strict)
    store.commit_projection(
        'synthetic',
        token,
        {'r': {'id': 'r', 'recording': True, '_v3_revision': 1}},
        {},
        [_broken('c')],
        [],
        firestore_client=strict,
    )
    assert strict.rows[C]['id'] == 'c' and strict.rows[R]['v3_pending'] is False


def test_v3_invalid_row_conflict_is_a_parked_deterministic_block():
    from utils.conversations.v3 import service

    assert 'invalid_row' in service.BLOCKED


def test_list_read_skips_only_the_malformed_row(caplog):
    rows = [_row('a'), _broken('bad'), 'not-a-row', _row('b')]
    before = _skips()
    with caplog.at_level(logging.WARNING, logger=row_contract.__name__):
        kept = row_contract.readable_rows(rows, surface='unit')
    assert kept == [rows[0], rows[3]] and kept[0] is rows[0]
    assert _skips() == before + 2
    assert 'surface=unit conversation_id=bad' in caplog.text and SECRET not in caplog.text
    assert [c.id for c in row_contract.readable_models(rows, surface='unit', model=Conversation)] == ['a', 'b']


@pytest.mark.parametrize(
    'malformed',
    [
        _broken(),
        _row('bad', structured=[], is_locked=True),
        _row('bad', structured=['invalid']),
        _row('bad', structured=None, is_locked=True),
    ],
    ids=['participant-source', 'empty-list', 'nonempty-list', 'null'],
)
def test_get_conversations_returns_the_rest_of_a_page_with_one_malformed_row(monkeypatch, caplog, malformed):
    from utils.episodes import home_membership

    page = [_row('a'), malformed, _row('b', is_locked=True, structured={'action_items': 'redacted on list reads'})]
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'true')
    monkeypatch.setattr(routes, 'home_transcription_presentation_gate_enabled', lambda: False)
    monkeypatch.setattr(home_membership, 'held_for', lambda request: False)
    monkeypatch.setattr(home_membership, 'live_suppression_for', lambda *a: False)
    monkeypatch.setattr(home_membership, 'project_list', lambda uid, rows, *a, **kw: rows)
    monkeypatch.setattr(
        routes.ListVersionCheck, 'start', lambda *a: SimpleNamespace(not_modified=None, finish=lambda *a, **kw: None)
    )
    monkeypatch.setattr(
        routes,
        'list_read_budget_for_request',
        lambda *a, **kw: SimpleNamespace(truncated=False, observe=lambda outcome: None),
    )
    monkeypatch.setattr(db, 'get_conversations_without_photos', lambda *a, **kw: [dict(row) for row in page])
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'synthetic'
    before = _skips()
    with TestClient(app) as client:
        response = client.get('/v1/conversations')

    assert response.status_code == 200
    result = response.json()
    assert [row['id'] for row in result] == ['a', 'b']
    assert result[0]['home_step'] == 'ready'
    assert result[1]['structured']['action_items'] == []
    assert _skips() == before + 1
    assert 'surface=v1_conversations conversation_id=bad' in caplog.text


async def test_search_exact_reference_drops_a_malformed_row(monkeypatch):
    from models.conversation import SearchRequest

    monkeypatch.setattr(db, 'get_conversations_by_id_without_photos', lambda *a, **kw: [_broken('bad'), _row('a')])
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    result = await routes._search_exact_conversation_reference(
        'bad', SearchRequest(query='bad'), 'synthetic', None, None
    )
    assert [row['id'] for row in result['items']] == ['a']


async def test_speaker_browse_drops_a_malformed_row(monkeypatch):
    from models.conversation import SearchRequest

    monkeypatch.setattr(routes.conversation_scan_db, 'conversation_scan_budget', lambda *a, **kw: None)
    monkeypatch.setattr(routes.conversation_scan_db, 'speaker_browse_scan', lambda *a, **kw: [])
    monkeypatch.setattr(
        routes,
        'browse_conversations_by_speaker',
        lambda *a, **kw: {'items': [_broken('bad'), _row('a')], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
    )
    monkeypatch.setattr(
        routes.paid_lock_recovery,
        'PaidLockRecovery',
        lambda uid: SimpleNamespace(can_recover=None, heal=lambda rows: None),
    )
    monkeypatch.setattr(routes, 'finish_list_budget', lambda *a: None)
    result = await routes._browse_speaker_conversations(
        SearchRequest(speaker_id='spk'), 'synthetic', None, None, None, None
    )
    assert [row['id'] for row in result['items']] == ['a']
