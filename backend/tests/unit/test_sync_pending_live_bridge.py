"""A live overlap hint holds standalone visibility until proof, keep or expiry."""

from copy import deepcopy
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as db
from tests.unit.test_sync_live_overlap import assign, live_row, seeded
from tests.unit.test_sync_cross_job_assignment import chunk
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing, _rows_from_store
from utils.sync import bridge, bridge_pending
from utils.sync.intake_completion import complete_sync_intake


@pytest.fixture
def pending(monkeypatch):
    # The live owner exists but has not yet persisted speech proof. Its wall
    # envelope may hold intake, but cannot authorize transcript transfer.
    live = live_row('in_progress')
    live.update(has_content=False, transcript_segments=[])
    store = seeded(live)
    incoming = dict(
        chunk('wal', 1002),
        data_protection_level='standard',
        structured={'title': 'Retained speech', 'title_provenance': 'server_minimum'},
    )
    row, created, survivors = assign(store, incoming)
    assert created and row['id'] == 'wal' and bridge_pending.hidden(row)
    assert not row['discarded']
    monkeypatch.setattr(
        bridge,
        'read_metadata',
        lambda _, uid, cid, **kw: deepcopy(store.rows.get(('users', uid, 'conversations', cid))),
    )
    monkeypatch.setattr(
        db, 'get_conversation', lambda uid, cid, **kw: deepcopy(store.rows.get(('users', uid, 'conversations', cid)))
    )
    monkeypatch.setattr(db, 'assign_sync_conversation', lambda uid, row, **kw: assign(store, row, **kw))
    monkeypatch.setattr(bridge, 'transfer_donor', lambda *a: None)
    monkeypatch.setattr(bridge, 'retract_sync_bridge_source', lambda *a: None)
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', lambda *a: True)
    return store, row, created, survivors


def test_default_list_and_count_hide_pending_but_expiry_or_keep_releases_it(monkeypatch, pending):
    store, row, _, _ = pending
    _install_listing(monkeypatch, _rows_from_store(store))
    assert db.get_conversations_without_photos('u', statuses=['completed']) == []
    assert db.get_conversations_count('u', statuses=['completed']) == 0
    assert [
        r['id'] for r in db.get_conversations_without_photos('u', statuses=['completed'], include_discarded=True)
    ] == ['wal']
    saved = store.rows[('users', 'u', 'conversations', 'wal')]
    deadline = saved[bridge_pending.FIELD]['expires_at']
    monkeypatch.setattr(bridge_pending, 'current_time', lambda: deadline)
    _install_listing(monkeypatch, _rows_from_store(store))
    assert [r['id'] for r in db.get_conversations_without_photos('u', statuses=['completed'])] == ['wal']
    assert db.get_conversations_count('u', statuses=['completed']) == 1
    assert db.is_visible_conversation(dict(row, sync_relevance_user_kept=True))


def test_pending_deadline_is_not_extended_by_more_intake(pending):
    store, row, _, _ = pending
    again, _, _ = assign(
        store, dict(chunk('more', 1003, text='Another retained observation.'), data_protection_level='standard')
    )
    assert again[bridge_pending.FIELD] == row[bridge_pending.FIELD]


@pytest.mark.parametrize('finished_status', ['processing', 'completed'])
@pytest.mark.parametrize('expired', [False, True])
def test_live_target_is_bridged_after_capture_finishes(monkeypatch, pending, finished_status, expired):
    from utils.enrichment import callback
    from utils.conversations.summary_delivery import PROCESS_CONTEXT

    store, row, _, _ = pending
    if expired:
        deadline = row[bridge_pending.FIELD]['expires_at']
        monkeypatch.setattr(bridge_pending, 'current_time', lambda: deadline + 1)
    context = {}
    token = PROCESS_CONTEXT.set(context)
    try:
        callback.enrich_conversation('u', 'wal', 'en')
        assert context['defer_reason'] == 'pending_live_bridge'
        if expired:
            assert context['defer_until'] > row[bridge_pending.FIELD]['expires_at']
        else:
            assert context['defer_until'] <= row[bridge_pending.FIELD]['expires_at']
        store.rows[('users', 'u', 'conversations', 'live')].update(live_row(finished_status))
        context.clear()
        callback.enrich_conversation('u', 'wal', 'en')
        assert context == {'redirect_to': 'live'}
    finally:
        PROCESS_CONTEXT.reset(token)
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'live'
    canonical = store.rows[('users', 'u', 'conversations', 'live')]
    assert 'wal' in canonical['sync_merged_from']
    assert not bridge_pending.hidden(canonical)
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    _install_listing(monkeypatch, _rows_from_store(store))
    assert [r['id'] for r in db.get_conversations_without_photos('u')] == ['live']


def test_pending_review_intake_enrolls_bridge_even_without_audio(monkeypatch, pending):
    _, row, created, survivors = pending
    row['sync_relevance'] = 'review'
    response = {'new_memories': set(), 'updated_memories': set()}
    finish = MagicMock()
    complete_sync_intake(
        uid='u',
        assigned=row,
        created=created,
        survivors=survivors,
        response=response,
        lock=threading.Lock(),
        language='en',
        audio_enabled=False,
        store_audio=lambda _: None,
        finish=finish,
        mark_finalize=lambda: None,
        acknowledge=lambda: None,
    )
    assert response['_merged'] == {'wal': 'en'}
    finish.assert_called_once()


@pytest.mark.parametrize('indexed', [False, True])
def test_default_home_http_list_hides_pending_row(monkeypatch, pending, indexed):
    from routers import conversations as routes
    from utils.other import endpoints as auth
    from tests.unit.test_sync_donor_tombstone_visibility import _ListingCollection, _ListingDoc, _ListingQuery

    def select(collection, fields):
        return _ListingQuery(
            [
                _ListingDoc(doc.id, {key: value for key, value in doc.to_dict().items() if key in fields})
                for doc in collection._query._docs
            ]
        )

    monkeypatch.setattr(_ListingCollection, 'select', select, raising=False)
    monkeypatch.setattr(db, 'indexed_list_reads_enabled', lambda: indexed)
    store, _, _, _ = pending
    _install_listing(monkeypatch, _rows_from_store(store))
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(
        routes.ListVersionCheck, 'start', lambda *a: SimpleNamespace(not_modified=None, finish=lambda *a, **kw: None)
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.get('/v1/conversations')
        assert response.status_code == 200
        assert response.json() == []
        assert client.get('/v1/conversations/wal').status_code == 404
        store.rows[('users', 'u', 'conversations', 'wal')]['sync_relevance_user_kept'] = True
        _install_listing(monkeypatch, _rows_from_store(store))
        response = client.get('/v1/conversations')
        assert response.status_code == 200
        assert [row['id'] for row in response.json()] == ['wal']


def test_pending_bridge_preserves_an_independently_enriched_donor(pending):
    store, _, _, _ = pending
    source = store.rows[('users', 'u', 'conversations', 'wal')]
    source['structured'] = {'title': 'Generated notes', 'overview': 'Existing protected notes.'}
    store.rows[('users', 'u', 'conversations', 'live')].update(live_row('completed'))
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_content_revision')


def test_sync_enrichment_yields_to_a_bound_processing_finalizer(monkeypatch, pending):
    from utils.enrichment import callback
    from utils.conversations.summary_delivery import PROCESS_CONTEXT

    store, _, _, _ = pending
    store.rows[('users', 'u', 'conversations', 'live')].update(
        live_row('processing'), sync_live_target=True, finalization_job_id='job'
    )
    process = MagicMock()
    monkeypatch.setattr(callback, 'process_conversation', process)
    context = {}
    token = PROCESS_CONTEXT.set(context)
    try:
        callback.enrich_conversation('u', 'live', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    assert context == {'defer_reason': 'open_live_target'}
    process.assert_not_called()


def test_flags_off_preserve_standalone_intake_and_skip_target_recovery(monkeypatch):
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    monkeypatch.setenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', 'false')
    live = live_row('in_progress')
    live.update(has_content=False, transcript_segments=[])
    store = seeded(live)
    original = deepcopy(store.rows)
    row, created, _ = assign(store, dict(chunk('wal', 1002), data_protection_level='standard'))
    assert created and row['id'] == 'wal'
    assert not row.get(bridge_pending.FIELD)
    assert db.is_visible_conversation(row)
    assert store.rows[('users', 'u', 'conversations', 'live')] == original[('users', 'u', 'conversations', 'live')]
    monkeypatch.setattr(bridge, 'read_metadata', lambda *a, **kw: deepcopy(row))
    recover = MagicMock(side_effect=AssertionError('flag-off must not recover a target'))
    monkeypatch.setattr(bridge, '_finish_pending_live_bridge', recover)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    recover.assert_not_called()
