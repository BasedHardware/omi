"""Completed rule-discard sync fragments hide on their decision, not a stored flag.

Incident shape: a sync row finished as ``sync_live_target`` with shared
visibility stayed ``discarded=False`` because intake treated live ownership
and sharing as curation. A completed, uncurated row whose stored
``relevance_decision`` is a ``rule`` verdict of ``discard`` must read as
discarded everywhere; the stored row itself is never rewritten by reads.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from tests.unit.test_sync_donor_tombstone_visibility import (
    _ListingQuery as _ListingSpy,
)
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing


def _visible_row(when: datetime, row_id: str = 'visible') -> dict:
    return {
        'id': row_id,
        'created_at': when,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': 'Real conversation'},
    }


def _incident(**overrides):
    row = {
        'id': 'incident',
        'created_at': datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        'started_at': datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 9, 22, 12, 2, tzinfo=timezone.utc),
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'sync_live_target': True,
        'sync_relevance': 'review',
        'visibility': 'shared',
        'sync_content_revision': 3,
        'structured': {'title': '', 'overview': '', 'sections': [], 'action_items': [], 'events': []},
        'relevance_decision': {
            'verdict': 'discard',
            'decided_by': 'rule',
            'reason': 'no_content_words',
            'trigger': 'capture_end',
            'rules_version': 3,
        },
        'transcript_segments': [
            {
                'start': 0.0,
                'end': 2.0,
                'text': 'I think it is.',
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': False,
            }
        ],
    }
    row.update(overrides)
    return row


def test_is_completed_rule_discard_matches_only_the_incident_shape():
    from utils.conversations.fragment_visibility import is_completed_rule_discard

    assert is_completed_rule_discard(_incident())
    assert is_completed_rule_discard(_incident(status=SimpleNamespace(value='completed')))
    assert is_completed_rule_discard(_incident(sync_live_target=False, visibility='private'))
    for overrides in (
        {'status': 'in_progress'},
        {'status': 'processing'},
        {'sync_relevance_user_kept': True},
        {'user_title': 'Named'},
        {'starred': True},
        {'folder_user_set': True},
        {'has_photos': True},
        {'photos': [{'id': 'p'}]},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'model', 'reason': 'model_discard'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'jev', 'reason': 'jev_discard'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'other_reason'}},
        {'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'no_content_words'}},
        {'relevance_decision': 'not-a-mapping'},
        {'relevance_decision': None},
    ):
        assert not is_completed_rule_discard(_incident(**overrides)), overrides
    assert not is_completed_rule_discard(None)


def test_live_ownership_and_sharing_no_longer_count_as_curation():
    from utils.conversations.fragment_visibility import is_low_signal_sync_fragment, is_user_curated

    assert not is_user_curated(_incident())
    assert is_low_signal_sync_fragment(_incident())
    assert not is_low_signal_sync_fragment(_incident(status='in_progress'))
    for still_curated in (
        {'sync_relevance_user_kept': True},
        {'has_photos': True},
        {'photos': [{'id': 'p'}]},
        {'user_title': 'Named'},
        {'starred': True},
        {'folder_user_set': True},
    ):
        row = _incident(**still_curated)
        assert is_user_curated(row), still_curated
        assert not is_low_signal_sync_fragment(row), still_curated


@pytest.fixture
def conversations_db(monkeypatch):
    from database import conversations

    _install_listing(monkeypatch, {'incident': _incident()})
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', MagicMock())
    return conversations


def test_default_list_omits_a_completed_rule_discard(conversations_db):
    default = conversations_db.get_conversations_without_photos('u', limit=10, offset=0)
    assert 'incident' not in {row['id'] for row in default}

    archive = conversations_db.get_conversations_without_photos('u', limit=10, offset=0, include_discarded=True)
    (incident,) = [row for row in archive if row['id'] == 'incident']
    assert incident['discarded'] is True


def test_limit_one_page_fills_past_a_completed_rule_discard(monkeypatch):
    from database import conversations as conversations_db

    newer = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)
    older = datetime(2026, 9, 22, 11, 0, tzinfo=timezone.utc)
    visible = {
        'id': 'visible',
        'created_at': older,
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': 'Real conversation'},
    }
    _install_listing(monkeypatch, {'incident': _incident(created_at=newer), 'visible': visible})

    page = conversations_db.get_conversations_without_photos('u', limit=1, offset=0)
    assert [row['id'] for row in page] == ['visible']


def test_mixed_page_fills_past_a_later_stale_rule_discard(monkeypatch):
    from database import conversations as conversations_db

    def _at(hour: int) -> datetime:
        return datetime(2026, 9, 22, hour, 0, tzinfo=timezone.utc)

    visible_new = {
        'id': 'visible-new',
        'created_at': _at(14),
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': 'Newer real conversation'},
    }
    visible_old = {
        'id': 'visible-old',
        'created_at': _at(11),
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': 'Older real conversation'},
    }
    _install_listing(
        monkeypatch,
        {
            'visible-new': visible_new,
            'stale-1': _incident(id='stale-1', created_at=_at(13)),
            'stale-2': _incident(id='stale-2', created_at=_at(12)),
            'visible-old': visible_old,
        },
    )

    page = conversations_db.get_conversations_without_photos('u', limit=2, offset=0)
    assert [row['id'] for row in page] == ['visible-new', 'visible-old']


def test_default_list_sends_limit_then_offset_and_refill_stays_capped(monkeypatch):
    """Desktop parity: the first query must carry server limit+offset, and the
    refill must give up after the 64-skip cap instead of walking the collection."""
    from database import conversations as conversations_db
    from datetime import timedelta

    calls = []
    real_limit = _ListingSpy.limit
    real_offset = _ListingSpy.offset
    real_stream = _ListingSpy.stream

    def limit(self, value):
        calls.append(('limit', value))
        return real_limit(self, value)

    def offset(self, value):
        calls.append(('offset', value))
        return real_offset(self, value)

    def stream(self, **kwargs):
        calls.append(('stream', self._offset, self._limit, self._start_after_id))
        return real_stream(self, **kwargs)

    monkeypatch.setattr(_ListingSpy, 'limit', limit)
    monkeypatch.setattr(_ListingSpy, 'offset', offset)
    monkeypatch.setattr(_ListingSpy, 'stream', stream)

    # First page: one visible row, then 70 consecutive stale rule-discards
    # (above the 64-skip cap), then a deep visible row. The refill must stop
    # at the cap; reaching the deep row means the cap is gone.
    base = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    rows = {'visible': _visible_row(base + timedelta(minutes=100))}
    for n in range(1, 71):
        rows[f'stale-{n}'] = _incident(id=f'stale-{n}', created_at=base + timedelta(minutes=100 - n))
    rows['deep-visible'] = _visible_row(base, row_id='deep-visible')
    _install_listing(monkeypatch, rows)

    page = conversations_db.get_conversations_without_photos('u', limit=2, offset=0)
    ids = [row['id'] for row in page]

    # limit+offset order on the first query (desktop backend contract)
    first_limit = next(i for i, c in enumerate(calls) if c[0] == 'limit')
    assert calls[first_limit] == ('limit', 2)
    assert calls[first_limit + 1] == ('offset', 0)
    # the refill read is bounded: 70 skips at window 2 = 35 batches, capped
    refill_streams = [c for c in calls if c[0] == 'stream' and c[3] is not None]
    assert len(refill_streams) <= 36
    # the cap stopped the scan: the page is short, never wrong
    assert ids == ['visible']
    # sanity: without the cap the deep row would exist in this listing
    assert any(doc_id == 'deep-visible' for doc_id in rows)


def test_read_projection_marks_the_incident_without_mutating_it(conversations_db):
    stored = _incident()
    projected = conversations_db.prepare_conversation_for_read(stored, 'u')
    assert projected['discarded'] is True
    assert stored['discarded'] is False
    assert conversations_db.is_visible_conversation(stored) is False
    assert conversations_db.is_visible_conversation(stored, include_discarded=True) is True


def test_router_detail_projects_discard_by_default_and_hides_on_request(conversations_db, monkeypatch):
    from routers import conversations as routes

    stored = _incident()
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        lambda *a, **k: conversations_db.prepare_conversation_for_read(stored, 'u'),
    )

    detail = routes.get_conversation_by_id(
        'incident',
        source=None,
        include_discarded=True,
        uid='u',
        include_translations=False,
        translation_cursor=None,
        response=None,
    )
    assert detail['discarded'] is True

    for source in (None, 'omi'):
        with pytest.raises(HTTPException) as exc:
            routes.get_conversation_by_id(
                'incident',
                source=source,
                include_discarded=False,
                uid='u',
                include_translations=False,
                translation_cursor=None,
                response=None,
            )
        assert exc.value.status_code == 404
    assert stored['discarded'] is False


@pytest.mark.parametrize(
    'overrides',
    [
        {'status': 'in_progress'},
        {'sync_relevance_user_kept': True},
        {'user_title': 'Named'},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'model', 'reason': 'model_discard'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'jev', 'reason': 'jev_discard'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'other_reason'}},
        {'relevance_decision': None},
    ],
)
def test_non_incident_rows_stay_visible(monkeypatch, overrides):
    from database import conversations

    _install_listing(monkeypatch, {'row': _incident(id='row', **overrides)})
    listed = conversations.get_conversations_without_photos('u', limit=10, offset=0)
    assert [row['id'] for row in listed] == ['row']
    assert listed[0].get('discarded') is not True


def test_stored_discard_without_a_rule_decision_behaves_as_before(monkeypatch):
    from database import conversations

    _install_listing(monkeypatch, {'row': _incident(id='row', discarded=True, relevance_decision=None)})
    assert conversations.get_conversations_without_photos('u', limit=10, offset=0) == []
    (listed,) = conversations.get_conversations_without_photos('u', limit=10, offset=0, include_discarded=True)
    assert listed['discarded'] is True


def _stored(store, conversation_id):
    return store.rows[('users', 'u', 'conversations', conversation_id)]


_RULE_DISCARD_TEXTS = [
    ('I think it is.', 'no_content_words'),
    ('Mm-hmm.', 'filler_only'),
    ('testing one two three', 'mic_check'),
    ('', 'empty_transcript'),
]


@pytest.mark.parametrize(('text', 'reason'), _RULE_DISCARD_TEXTS)
def test_completed_live_shared_rule_discard_stays_hidden_on_append(text, reason):
    store = StrictFirestore()
    incident = chunk('incident', 1000, text)
    incident['structured'] = {'title': '', 'overview': ''}
    intake(store, incident)
    _stored(store, 'incident').update(discarded=False, sync_live_target=True, visibility='shared')

    appended = chunk('more', 1060, 'Hmm.' if text else '')
    result, created, _ = intake(store, appended, target_id='incident')

    assert not created and result['id'] == 'incident'
    assert result['discarded'] is True
    assert _stored(store, 'incident')['discarded'] is True
    decision = _stored(store, 'incident')['relevance_decision']
    assert decision['verdict'] == 'discard' and decision['decided_by'] == 'rule'
    assert decision['reason'] == reason
    assert result['sync_live_target'] is True


def test_empty_segment_append_is_a_dedupe_noop_and_leaves_stored_state():
    store = StrictFirestore()
    incident = chunk('incident', 1000, 'I think it is.')
    incident['structured'] = {'title': '', 'overview': ''}
    intake(store, incident)
    _stored(store, 'incident').update(discarded=False, sync_live_target=True, visibility='shared')

    appended = chunk('more', 1060, '')
    appended['transcript_segments'] = []
    result, created, _ = intake(store, appended, target_id='incident')

    assert not created and result['id'] == 'incident'
    assert _stored(store, 'incident')['discarded'] is False
    assert _stored(store, 'incident')['relevance_decision']['reason'] == 'no_content_words'


def test_second_filler_merge_keeps_a_rule_discard_hidden():
    store = StrictFirestore()
    first, _, _ = intake(store, chunk('filler', 1000, 'Mm-hmm.'))
    assert first['discarded'] is True
    again, created, _ = intake(store, chunk('more', 1060, 'Hmm.'), target_id='filler')
    assert not created
    assert again['discarded'] is True
    assert _stored(store, 'filler')['relevance_decision']['decided_by'] == 'rule'


def test_substantive_speech_promotes_and_drops_the_stale_rule_decision():
    store = StrictFirestore()
    first, _, _ = intake(store, chunk('filler', 1000, 'Mm-hmm.'))
    assert first['discarded'] is True

    promoted, created, _ = intake(store, chunk('speech', 1060, 'Please call the doctor tomorrow.'), target_id='filler')
    assert not created and promoted['id'] == 'filler'
    assert promoted['discarded'] is False
    assert promoted['sync_relevance'] == 'keep'
    assert promoted.get('relevance_decision') is None
    assert _stored(store, 'filler').get('relevance_decision') is None


@pytest.mark.parametrize('curation', [{'sync_relevance_user_kept': True}, {'user_title': 'Saved note'}])
def test_curated_rule_discard_is_visible_and_kept(curation):
    store = StrictFirestore()
    intake(store, chunk('filler', 1000, 'Mm-hmm.'))
    _stored(store, 'filler').update(discarded=False, **curation)

    result, _, _ = intake(store, chunk('more', 1060, 'Hmm.'), target_id='filler')
    assert result['discarded'] is False
    assert result['sync_relevance'] == 'keep'


def test_open_live_target_never_discards_mid_session():
    store = StrictFirestore()
    intake(store, chunk('live', 1000, 'Mm-hmm.'))
    _stored(store, 'live').update(discarded=False, status='in_progress', sync_live_target=True)

    result, _, _ = intake(store, chunk('more', 1060, 'Hmm.'), target_id='live')
    assert result['discarded'] is False


def test_merge_gates_still_reject_live_and_shared_rows():
    from utils.conversations.smart_merge_policy import user_managed
    from utils.sync.assignment import auto_mergeable

    base = {'sync_content_revision': 1}
    assert not auto_mergeable({**base, 'sync_live_target': True})
    assert not auto_mergeable({**base, 'visibility': 'shared'})
    assert user_managed({**base, 'visibility': 'shared'})


@pytest.fixture
def pipeline(monkeypatch):
    from database import conversations as conversations_db
    from utils.sync import pipeline as module

    calls = []
    real = module.lifecycle_service.discard_by_relevance

    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(module.lifecycle_service, 'discard_by_relevance', tracked)
    return module, conversations_db, calls


def _wire_store(monkeypatch, pipeline, conversations_db, store):
    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(pipeline, 'process_conversation', MagicMock())
    monkeypatch.setattr(pipeline, 'record_conversation_relevance', MagicMock())


def _stub_read(monkeypatch, conversations_db, row):
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        lambda *a, **k: conversations_db.prepare_conversation_for_read(deepcopy(row), 'u'),
    )


@pytest.mark.parametrize(('text', 'reason'), _RULE_DISCARD_TEXTS)
def test_pipeline_persists_the_rule_discard_before_returning(pipeline, monkeypatch, text, reason):
    module, conversations_db, calls = pipeline
    segments = [{'start': 0.0, 'end': 2.0, 'text': text, 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'is_user': False}]
    row = _incident(transcript_segments=segments if text else [])
    store = StrictFirestore({('users', 'u', 'conversations', 'incident'): deepcopy(row)})
    _wire_store(monkeypatch, module, conversations_db, store)
    _stub_read(monkeypatch, conversations_db, row)

    module._reprocess_conversation_after_update('u', 'incident', 'en')

    module.process_conversation.assert_not_called()
    stored = store.rows[('users', 'u', 'conversations', 'incident')]
    assert stored['discarded'] is True
    assert stored['relevance_decision']['verdict'] == 'discard'
    assert stored['relevance_decision']['decided_by'] == 'rule'
    assert stored['relevance_decision']['reason'] == reason
    assert calls and calls[0][1]['expected_sync_content_revision'] == 3
    module.record_conversation_relevance.assert_called_once()


def test_pipeline_discard_refuses_a_revised_or_newly_curated_row(pipeline, monkeypatch):
    module, conversations_db, calls = pipeline
    store = StrictFirestore({('users', 'u', 'conversations', 'incident'): _incident(sync_content_revision=4)})
    _wire_store(monkeypatch, module, conversations_db, store)
    _stub_read(monkeypatch, conversations_db, _incident())

    module._reprocess_conversation_after_update('u', 'incident', 'en')

    module.process_conversation.assert_not_called()
    module.record_conversation_relevance.assert_not_called()
    assert store.rows[('users', 'u', 'conversations', 'incident')]['discarded'] is False


@pytest.mark.parametrize('curation', [{'sync_relevance_user_kept': True}, {'user_title': 'Saved note'}])
def test_pipeline_keeps_curated_rows_on_the_processing_path(pipeline, monkeypatch, curation):
    module, conversations_db, calls = pipeline
    row = _incident(**curation)
    store = StrictFirestore({('users', 'u', 'conversations', 'incident'): deepcopy(row)})
    _wire_store(monkeypatch, module, conversations_db, store)
    _stub_read(monkeypatch, conversations_db, row)
    monkeypatch.setattr(module, 'deserialize_conversation', MagicMock())

    module._reprocess_conversation_after_update('u', 'incident', 'en')

    assert calls == []
    module.process_conversation.assert_called_once()
    assert module.process_conversation.call_args.kwargs['user_kept'] is True
    assert store.rows[('users', 'u', 'conversations', 'incident')]['discarded'] is False


def test_pipeline_never_hides_or_processes_an_open_live_row(pipeline, monkeypatch):
    module, conversations_db, calls = pipeline
    row = _incident(status='in_progress')
    store = StrictFirestore({('users', 'u', 'conversations', 'incident'): deepcopy(row)})
    _wire_store(monkeypatch, module, conversations_db, store)
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda *a, **k: deepcopy(row))

    module._reprocess_conversation_after_update('u', 'incident', 'en')

    assert calls == []
    module.process_conversation.assert_not_called()
    assert store.rows[('users', 'u', 'conversations', 'incident')]['discarded'] is False


def test_discard_by_relevance_refuses_newly_curated_and_non_completed(monkeypatch):
    from database import conversations

    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    decision = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}

    for blocker in (
        {'sync_relevance_user_kept': True},
        {'user_title': 'Named'},
        {'starred': True},
        {'folder_user_set': True},
        {'has_photos': True},
        {'status': 'in_progress'},
        {'deleted': True},
        {'discarded': True},
    ):
        store = StrictFirestore({('users', 'u', 'conversations', 'c'): _incident(**blocker)})
        monkeypatch.setattr(conversations, 'db', store)
        assert conversations.discard_by_relevance('u', 'c', decision) is False, blocker
        assert store.rows[('users', 'u', 'conversations', 'c')].get('discarded') is not True or blocker == {
            'discarded': True
        }

    store = StrictFirestore({('users', 'u', 'conversations', 'c'): _incident(sync_content_revision=7)})
    monkeypatch.setattr(conversations, 'db', store)
    assert conversations.discard_by_relevance('u', 'c', decision, expected_sync_content_revision=3) is False
    assert store.rows[('users', 'u', 'conversations', 'c')]['discarded'] is False
    assert conversations.discard_by_relevance('u', 'c', decision, expected_sync_content_revision=7) is True
    assert store.rows[('users', 'u', 'conversations', 'c')]['discarded'] is True

    assert conversations.discard_by_relevance('u', 'missing', decision) is False


def test_kept_empty_capture_gets_the_deterministic_title(monkeypatch):
    from models.conversation import Conversation
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import process_conversation as process
    from utils.conversations.deterministic_minimum import deterministic_minimum_title

    monkeypatch.setattr(process.notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    conversation = Conversation(
        id='kept-empty',
        created_at=now,
        started_at=now,
        finished_at=now,
        source='omi',
        structured=Structured(title=''),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1', text='I think it is.', speaker='SPEAKER_00', speaker_id=0, is_user=False, start=0.0, end=2.0
            )
        ],
    )
    structured = Structured(title='')

    result = process._get_conversation_obj('u', structured, conversation, 'kept-empty', relevance_discarded=False)

    assert result.discarded is False
    assert result.structured.title == deterministic_minimum_title(conversation, tz_name_provider=lambda: 'UTC')
    assert result.structured.title.strip()


@pytest.mark.parametrize('reason', [['no_content_words'], {'r': 'no_content_words'}, None, 7])
def test_malformed_rule_reason_never_raises_or_hides(reason):
    from database import conversations

    row = _incident(relevance_decision={'verdict': 'discard', 'decided_by': 'rule', 'reason': reason})
    projected = conversations.prepare_conversation_for_read(deepcopy(row), 'u')
    assert projected['discarded'] is False
    assert conversations.is_visible_conversation(row) is True
    assert conversations.is_visible_conversation(row, include_discarded=True) is True
    assert row['discarded'] is False
    assert not conversations.is_visible_conversation(_incident())


def test_detail_http_omitted_param_hides_a_rule_discard_and_keeps_a_stored_discard(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import conversations as conversations_db
    from routers import conversations as routes
    from utils.other import endpoints as auth

    stored = _incident()
    archived = {
        'id': 'archived',
        'created_at': datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
        'started_at': datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 9, 22, 10, 2, tzinfo=timezone.utc),
        'status': 'completed',
        'discarded': True,
        'deleted': False,
        'source': 'omi',
        'structured': {'title': 'Kept discard'},
    }
    rows = {'incident': stored, 'archived': archived}

    def _get(uid, conversation_id, **_kwargs):
        row = rows.get(conversation_id)
        return conversations_db.prepare_conversation_for_read(deepcopy(row), uid) if row else None

    monkeypatch.setattr(conversations_db, 'get_conversation', _get)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    client = TestClient(app)

    default = client.get('/v1/conversations/incident')
    assert default.status_code == 404

    hidden = client.get('/v1/conversations/incident', params={'include_discarded': 'false'})
    assert hidden.status_code == 404

    shown = client.get('/v1/conversations/incident', params={'include_discarded': 'true'})
    assert shown.status_code == 200 and shown.json()['discarded'] is True

    kept = client.get('/v1/conversations/archived')
    assert kept.status_code == 200 and kept.json()['id'] == 'archived'
    assert stored['discarded'] is False
