"""Grouping path integration: real matcher and fenced StrictFirestore writer."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
from unittest.mock import MagicMock

import pytest

from database import capture_groups as groups_db
from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import duplicate_capture as policy
from utils.conversations.overlap_shared_speech import VERSION

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'synthetic-sentence-owner'
TEXTS = [
    'An orange telescope needs a polished mirror before our mountain observatory opens tomorrow morning',
    'Please deliver twelve wooden benches beside the eastern garden while gardeners plant violet flowers',
    'Our ceramic workshop will display handmade blue bowls near the central library next Saturday afternoon',
]


def path(cid, uid=UID):
    return ('users', uid, 'conversations', cid)


def row(cid, source='omi', device='pendant', offset=0):
    return {
        'id': cid,
        'source': source,
        'client_device_id': device,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=offset),
        'finished_at': T0 + timedelta(seconds=300),
        'external_data': {},
        'transcript_segments': [
            {'start': start - offset, 'end': start - offset + 8, 'text': text}
            for start, text in zip((60, 100, 140), TEXTS)
        ],
    }


@pytest.fixture
def store(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(policy, 'submit_same_scene', MagicMock())
    monkeypatch.setattr(policy, 'submit_resummary', MagicMock())
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_PERCENT', '100')
    monkeypatch.setenv('CAPTURE_GROUP_CONTAINMENT_MODE', 'off')
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', 'off')
    for key in (
        'CROSS_DEVICE_GROUP_MIN_WORDS',
        'CROSS_DEVICE_GROUP_MIN_SHARED_TRIGRAMS',
        'CROSS_DEVICE_GROUP_MIN_CONTAINMENT',
        'CROSS_DEVICE_DEDUP_MIN_OVERLAP_SECONDS',
        'CROSS_DEVICE_DEDUP_MIN_OVERLAP_RATIO',
    ):
        monkeypatch.delenv(key, raising=False)

    def query(uid, **kwargs):
        return [deepcopy(r) for p, r in store.rows.items() if p[:2] == ('users', uid)][: kwargs['limit']]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    return store


@pytest.mark.parametrize('source,device', [('desktop', 'mac'), ('omi', 'pendant'), ('omi', 'another'), ('omi', None)])
@pytest.mark.parametrize('last', ['a', 'b'])
def test_on_groups_all_pair_classes_in_both_orders_metadata_only(store, monkeypatch, source, device, last):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path('a'): row('a'), path('b'): row('b', source, device, offset=5)})
    before = deepcopy(store.rows)
    policy.link_duplicate_captures(UID, store.rows[path(last)])
    group = store.rows[path('a')]['capture_group']
    assert group == store.rows[path('b')]['capture_group']
    assert group['primary_id'] == 'a'
    assert {m['evidence']['method'] for m in group['members']} == {VERSION}
    for cid in ('a', 'b'):
        assert {k: v for k, v in store.rows[path(cid)].items() if k not in ('capture_group', 'external_data')} == {
            k: v for k, v in before[path(cid)].items() if k not in ('capture_group', 'external_data')
        }
    policy.link_duplicate_captures(UID, store.rows[path(last)])
    assert store.rows[path('a')]['capture_group']['revision'] == group['revision']
    groups_db.leave_capture_group(UID, 'b', sticky=True)
    policy.link_duplicate_captures(UID, store.rows[path('a')])
    assert not store.rows[path('a')].get('capture_group')
    assert not store.rows[path('b')].get('capture_group')


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_dark_and_shadow_keep_same_source_separate(store, monkeypatch, mode, caplog):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', mode)
    store.rows.update({path('a'): row('a'), path('b'): row('b')})
    before = deepcopy(store.rows)
    with caplog.at_level(logging.INFO, logger=policy.logger.name):
        policy.link_duplicate_captures(UID, store.rows[path('a')])
    assert store.rows == before
    lines = [r.message for r in caplog.records if r.message.startswith('capture_shared_speech ')]
    assert len(lines) == (1 if mode == 'shadow' else 0)
    if lines:
        data = json.loads(lines[0].split(' ', 1)[1])
        assert data['would_join'] and not data['current_would_join']
        assert data['category'] == 'same_source_same_device'
        assert all(text not in lines[0] for text in TEXTS)


@pytest.mark.parametrize('mode,joins', [('off', True), ('shadow', True), ('on', False)])
def test_same_full_text_outside_overlap_cannot_authorize_new_fold(store, monkeypatch, mode, joins):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', mode)
    first, second = row('a'), row('b', 'desktop', 'mac')
    second['started_at'] = T0 + timedelta(seconds=150)
    second['finished_at'] = T0 + timedelta(seconds=320)
    # Full-transcript trigrams agree, but speech occurred before/after shared time.
    second['transcript_segments'] = deepcopy(first['transcript_segments'])
    store.rows.update({path('a'): first, path('b'): second})
    policy.link_duplicate_captures(UID, first)
    assert bool(store.rows[path('a')].get('capture_group')) is joins


@pytest.mark.parametrize('change', ['transcript', 'window', 'deleted', 'discarded', 'closed', 'separate'])
def test_writer_rechecks_after_new_confirmation(store, monkeypatch, change):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path('a'): row('a'), path('b'): row('b')})
    original = groups_db.join_capture_group

    def race(*args, **kwargs):
        target = store.rows[path('b')]
        if change == 'transcript':
            target['transcript_segments'][0]['text'] = 'new corrected transcript'
        elif change == 'window':
            target['finished_at'] += timedelta(seconds=1)
        elif change == 'separate':
            target['capture_group_exclusions'] = ['a']
        else:
            target['capture_group_closed' if change == 'closed' else change] = True
        return original(*args, **kwargs)

    monkeypatch.setattr(groups_db, 'join_capture_group', race)
    policy.link_duplicate_captures(UID, store.rows[path('a')])
    assert not store.rows[path('a')].get('capture_group')


def test_on_preserves_existing_folds_and_other_accounts(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path('a'): row('a'), path('b'): row('b'), path('other', 'different-owner'): row('other')})
    policy.link_duplicate_captures(UID, store.rows[path('a')])
    group = deepcopy(store.rows[path('a')]['capture_group'])
    store.rows[path('b')]['transcript_segments'] = []
    policy.link_duplicate_captures(UID, store.rows[path('a')])
    assert store.rows[path('a')]['capture_group'] == group
    assert not store.rows[path('other', 'different-owner')].get('capture_group')


def test_on_does_not_allow_complementary_call_policy_to_bypass_speech(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    monkeypatch.setenv('DESKTOP_PENDANT_CALL_LINK_MODE', 'on')
    first, second = row('a'), row('b', 'desktop', 'mac')
    second['external_data']['conversation_role'] = 'meeting'
    second['transcript_segments'] = []
    store.rows.update({path('a'): first, path('b'): second})
    policy.link_duplicate_captures(UID, first)
    assert all(not r.get('capture_group') for r in store.rows.values())


def test_selected_candidate_budget_is_bounded(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path(str(i)): row(str(i)) for i in range(20)})
    read = MagicMock(wraps=conversations_db.get_conversation_for_capture_check)
    monkeypatch.setattr(conversations_db, 'get_conversation_for_capture_check', read)
    policy.link_duplicate_captures(UID, store.rows[path('0')])
    assert read.call_count == 1 + policy.MAX_CONTENT_CHECKS


def test_optional_failure_is_content_free_and_does_not_raise(store, monkeypatch, caplog):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path('a'): row('a'), path('b'): row('b')})
    monkeypatch.setattr(policy, 'measure_overlap_shared_speech', MagicMock(side_effect=ValueError('private sentence')))
    with caplog.at_level(logging.WARNING):
        policy.link_duplicate_captures(UID, store.rows[path('a')])
    assert 'private sentence' not in caplog.text
    assert 'outcome=error' in caplog.text
