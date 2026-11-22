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
        'recorded_start': T0 + timedelta(seconds=offset),
        'recorded_end': T0 + timedelta(seconds=300),
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


def seed_group(store, ids):
    for cid in ids:
        store.rows[path(cid)] = row(cid)
    for cid in ids[1:]:
        assert groups_db.join_capture_group(UID, ids[0], cid, {'method': 'synthetic-prior-group'})


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
