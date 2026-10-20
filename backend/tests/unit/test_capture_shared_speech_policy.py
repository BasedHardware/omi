"""Grouping path integration: real matcher and fenced StrictFirestore writer."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
from unittest.mock import MagicMock

import pytest

from database import capture_groups as groups_db
from database import conversations as conversations_db
from database import capture_speech as speech_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
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
    monkeypatch.setattr(speech_db, 'get_firestore_client', lambda: store)
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_PERCENT', '100')
    monkeypatch.setenv('CAPTURE_GROUP_CONTAINMENT_MODE', 'off')
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


def test_on_requires_shared_speech_to_create_a_capture_group(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    first, second = row('a'), row('b', 'desktop', 'mac')
    second['external_data']['conversation_role'] = 'meeting'
    second['transcript_segments'] = []
    store.rows.update({path('a'): first, path('b'): second})
    policy.link_duplicate_captures(UID, first)
    assert all(not r.get('capture_group') for r in store.rows.values())


def test_selected_candidate_budget_is_bounded(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    store.rows.update({path(str(i)): row(str(i)) for i in range(20)})
    read = MagicMock(wraps=policy.get_shared_speech_snapshot)
    monkeypatch.setattr(policy, 'get_shared_speech_snapshot', read)
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


def seed_group(store, ids):
    for cid in ids:
        store.rows[path(cid)] = row(cid)
    for cid in ids[1:]:
        assert groups_db.join_capture_group(UID, ids[0], cid, {'method': 'synthetic-prior-group'})


def test_existing_group_grows_only_when_entrant_matches_every_member(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    seed_group(store, ['a', 'b'])
    store.rows[path('c')] = row('c')
    policy.link_duplicate_captures(UID, store.rows[path('c')])
    group = store.rows[path('c')]['capture_group']
    assert {member['id'] for member in group['members']} == {'a', 'b', 'c'}


def test_pairwise_match_does_not_bridge_different_speech_through_long_capture(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    seed_group(store, ['a', 'b'])
    for segment in store.rows[path('b')]['transcript_segments']:
        segment['text'] = 'a different private event with entirely unrelated vocabulary about zebra quartz tundra'
    store.rows[path('c')] = row('c')
    policy.link_duplicate_captures(UID, store.rows[path('c')])
    assert not store.rows[path('c')].get('capture_group')
    assert len(store.rows[path('a')]['capture_group']['members']) == 2


@pytest.mark.parametrize(
    'change',
    [
        'third_transcript',
        'group_revision',
        'discarded',
        'is_locked',
        'deleted',
        'capture_group_closed',
        'status',
        'correction',
        'pair_locked',
        'pair_correction',
    ],
)
def test_group_wide_evidence_is_fenced_at_commit(store, monkeypatch, change):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    seed_group(store, ['a', 'b'])
    store.rows[path('c')] = row('c')
    original = groups_db.join_capture_group

    def race(*args, **kwargs):
        if change == 'third_transcript':
            # The queried pair is c/a; b was checked as the additional member.
            store.rows[path('b')]['transcript_segments'][0]['text'] = 'an edited third transcript'
        elif change == 'group_revision':
            for cid in ('a', 'b'):
                store.rows[path(cid)]['capture_group']['revision'] += 1
        elif change in ('correction', 'pair_correction'):
            store.rows[path('c' if change == 'pair_correction' else 'b')]['has_transcript_corrections'] = True
        elif change == 'pair_locked':
            store.rows[path('c')]['is_locked'] = True
        else:
            store.rows[path('b')][change] = 'processing' if change == 'status' else True
        return original(*args, **kwargs)

    monkeypatch.setattr(groups_db, 'join_capture_group', race)
    policy.link_duplicate_captures(UID, store.rows[path('c')])
    assert not store.rows[path('c')].get('capture_group')


def test_large_group_abstains_without_exceeding_read_budget(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    seed_group(store, [str(i) for i in range(8)])
    store.rows[path('entrant')] = row('entrant')
    read = MagicMock(wraps=policy.get_shared_speech_snapshot)
    monkeypatch.setattr(policy, 'get_shared_speech_snapshot', read)
    policy.link_duplicate_captures(UID, store.rows[path('entrant')])
    assert not store.rows[path('entrant')].get('capture_group')
    assert read.call_count <= policy.MAX_CONTENT_CHECKS + 1


def test_corrected_capture_abstains_without_decoding_or_overlay_reads(store, monkeypatch):
    record = row('a')
    record['has_transcript_corrections'] = True
    store.rows[path('a')] = record
    decode = MagicMock(side_effect=AssertionError('corrected capture must not be decoded'))
    project = MagicMock(side_effect=AssertionError('no correction projection'))
    monkeypatch.setattr(speech_db, 'decode_capture_segments', decode)
    monkeypatch.setattr(conversations_db, 'prepare_conversation_for_read', project)
    snapshot, fingerprint = speech_db.get_shared_speech_snapshot(UID, 'a')
    assert snapshot['has_transcript_corrections'] and snapshot['transcript_segments'] == []
    assert fingerprint is None
    decode.assert_not_called()
    project.assert_not_called()


def test_incumbent_snapshot_conflict_does_not_read_additional_group_members(store, monkeypatch):
    seed_group(store, ['a', 'b', 'c'])
    store.rows[path('d')] = row('d')
    reads = []
    original = StrictFirestoreDocument.get

    def observe(reference, *args, **kwargs):
        if kwargs.get('transaction') is not None:
            reads.append(reference.path)
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', observe)
    assert groups_db.join_capture_group(UID, 'a', 'd', {}, expected_fingerprints={'a': 'stale'}) is None
    assert reads == [path('a'), path('d')]


def test_zero_revision_requires_absence_of_any_existing_group(store, monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    seed_group(store, ['a', 'b'])
    for cid in ('a', 'b'):
        store.rows[path(cid)]['capture_group'].pop('revision')
    store.rows[path('c')] = row('c')
    policy.link_duplicate_captures(UID, store.rows[path('c')])
    assert not store.rows[path('c')].get('capture_group')


def test_correction_comparison_is_unknown_instead_of_fabricating_incumbent_false(store, monkeypatch, caplog):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    first, second = row('a'), row('b', 'desktop', 'mac')
    first['has_transcript_corrections'] = True
    store.rows.update({path('a'): first, path('b'): second})
    with caplog.at_level(logging.INFO, logger=policy.logger.name):
        policy.link_duplicate_captures(UID, first)
    data = next(
        json.loads(r.message.split(' ', 1)[1]) for r in caplog.records if r.message.startswith('capture_shared_speech ')
    )
    assert data['current_would_join'] is None
    assert not data['would_join'] and data['reason'] == 'transcript_corrections'
