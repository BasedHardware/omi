"""Exercise catch-up coverage and cache identity through the real Firestore codec and transaction."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import conversations_v3 as store
from database import conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from utils.conversations.v3 import Conflict


def test_append_during_inference_preserves_coverage_and_same_clock_edit_invalidates_cache():
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')

    client = firestore.Client(project='demo-live-catchup', credentials=AnonymousCredentials())
    uid, cid = 'synthetic-' + uuid4().hex, 'episode'
    ref = store.user_conversations(client, uid).document(cid)
    start = datetime(2026, 11, 19, tzinfo=timezone.utc)
    initial_end = start + timedelta(seconds=30)
    segments = [{'start': 0, 'end': 30, 'text': 'synthetic speech ' * 160, 'speaker': 'SPEAKER_0'}]
    ref.set(
        {
            'id': cid,
            'created_at': start,
            'started_at': start,
            'finished_at': initial_end,
            'status': 'in_progress',
            'v3_derived': True,
            'v3_recording_ids': ['recording'],
            'data_protection_level': 'enhanced',
            'transcript_segments': segments,
        }
    )
    token = leases.acquire(uid, 'summary-' + cid, firestore_client=client)
    assert token
    assert leases.acquire(uid, 'summary-' + cid, firestore_client=client) is None

    def snapshot():
        row = store.decode_row(uid, ref.get())
        assert row is not None
        return row

    def commit(row):
        writers.store_summary(
            uid,
            cid,
            token,
            row['_v3_revision'],
            {'title': 'Planning', 'overview': 'We agreed to meet Friday.', 'sections': []},
            row['finished_at'],
            live_input=row,
            firestore_client=client,
        )

    frozen = snapshot()
    segments.append({'start': 31, 'end': 34, 'text': 'Additional speech.', 'speaker': 'SPEAKER_0'})
    ref.update(
        {
            'transcript_segments': segments,
            'finished_at': start + timedelta(seconds=34),
            'v3_recording_ids': ['recording', 'rotated'],
        }
    )
    commit(frozen)
    appended = snapshot()
    assert 'summary_covers_through' not in appended
    assert not appended.get('structured')
    preview = writers.read_live_summary(uid, appended)
    assert preview and preview['summary_covers_through'] == initial_end
    assert len(appended['transcript_segments']) == 2
    assert writers.read_live_summary(uid, appended, exact=True) is None
    changed_lineage = {**appended, 'v3_recording_ids': ['other', 'rotated']}
    assert writers.read_live_summary(uid, changed_lineage) is None
    commit(appended)
    cached = snapshot()
    preview = writers.read_live_summary(uid, cached, exact=True)
    assert preview and preview['structured']['overview'] == 'We agreed to meet Friday.'

    segments[-1]['text'] = 'Corrected speech.'
    ref.update({'transcript_segments': segments})
    assert writers.read_live_summary(uid, snapshot()) is None
    with pytest.raises(Conflict):
        commit(cached)
