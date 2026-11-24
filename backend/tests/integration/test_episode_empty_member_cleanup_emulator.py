"""Empty-live deletion and episode detachment share a real loopback transaction."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, current_thread
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import episode_empty_members, episode_timeline, recording_sessions
from utils.episodes.timeline import choose_recorded_episode

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('enabled,audio', [(True, False), (False, False), (True, True)])
def test_empty_cleanup_atomically_detaches_only_without_audio(monkeypatch, enabled, audio):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', str(enabled).lower())
    prepared = []
    prepare = episode_empty_members.prepare

    def observe_prepare(*args):
        writes = prepare(*args)
        prepared.extend((ref.path, update) for ref, update in writes)
        return writes

    monkeypatch.setattr(episode_empty_members, 'prepare', observe_prepare)
    client = firestore.Client(project='demo-episode-cleanup', credentials=AnonymousCredentials())
    try:
        uid = uuid4().hex
        root = client.collection('users').document(uid)
        conversation = root.collection('conversations').document('empty')
        episode = root.collection('episodes').document('episode')
        link = root.collection('episode_links').document('empty')
        session = root.collection('recording_sessions').document('session')
        row = {'status': 'in_progress', 'episode_id': episode.id, 'has_content': False}
        if audio:
            row['audio_files'] = [{'path': 'synthetic-audio'}]
        conversation.set(row)
        episode.set(
            {
                'status': 'closed',
                'state_version': 3,
                'conversation_ids': ['speech', 'empty'],
                'recorded_members': {'speech': {}, 'empty': {}},
                'content': b'preserved opaque content',
            }
        )
        link.set({'episode_id': episode.id})
        session.set(
            {
                'uid': uid,
                'recording_session_id': 'session',
                'conversation_id': 'empty',
                'lifecycle_phase': 'in_progress',
                'lifecycle_sequence': 2,
            }
        )
        assert recording_sessions.tombstone_and_delete_empty_conversation(
            uid, 'empty', 'session', firestore_client=client
        ) is (not audio)
        if enabled and not audio:
            assert any(path == link.path and update is None for path, update in prepared), prepared
        stored = episode.get().to_dict()
        assert stored['content'] == b'preserved opaque content'
        assert stored['status'] == 'closed'
        assert conversation.get().exists is audio
        # The existing Home writer may recreate a home_dirty-only preparation
        # marker in this same commit. Every ownership reader follows episode_id.
        linked = link.get().to_dict() or {}
        assert linked.get('episode_id') == (episode.id if audio or not enabled else None)
        assert stored['conversation_ids'] == (['speech'] if enabled and not audio else ['speech', 'empty'])
        assert session.get().to_dict()['lifecycle_phase'] == ('in_progress' if audio else 'discarded')
        if enabled and not audio:
            assert stored['state_version'] == 4
            assert stored['home_needs_prepare'] is True
            assert stored['recorded_members'] == {'speech': {}}
    finally:
        client.close()


@pytest.mark.parametrize('enabled', [True, False], ids=['cleanup-on', 'cleanup-off'])
def test_stub_cleanup_and_next_attach_commit_concurrently(monkeypatch, enabled):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', str(enabled).lower())
    monkeypatch.setenv('ENCRYPTION_SECRET', 'recorded_time_emulator_synthetic_key_32_bytes')
    client = firestore.Client(project='demo-episode-cleanup', credentials=AnonymousCredentials())
    try:
        uid = uuid4().hex
        root = client.collection('users').document(uid)
        start = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)

        def attach(cid, offset, choose=choose_recorded_episode):
            return episode_timeline.attach_recorded(
                uid,
                cid,
                'omi',
                start + timedelta(seconds=offset),
                start + timedelta(seconds=offset + 1),
                choose=choose,
                new_episode={},
                firestore_client=client,
            )

        # A retained member fixes the episode identity while a one-second live
        # stub and the reconnect's next capture share its recorded window.
        owner = attach('speech', 0)['id']
        assert attach('stub', 60)['id'] == owner
        conversation = root.collection('conversations').document('stub')
        conversation.set({'status': 'in_progress', 'episode_id': owner, 'has_content': False})
        root.collection('recording_sessions').document('session').set(
            {
                'uid': uid,
                'recording_session_id': 'session',
                'conversation_id': 'stub',
                'lifecycle_phase': 'in_progress',
                'lifecycle_sequence': 2,
            }
        )
        initial = root.collection('episodes').document(owner).get().to_dict()['state_version']
        barrier = Barrier(2)
        transactions = {}
        callback_attempts = {'cleanup': 0, 'attach': 0}
        original_transaction = client.transaction
        original_prepare = episode_empty_members.prepare

        def transaction(*args, **kwargs):
            name = current_thread().name
            transactions[name] = transactions.get(name, 0) + 1
            tx = original_transaction(*args, **kwargs)
            assert tx._max_attempts == 5  # Existing SDK budget; no new test retries.
            return tx

        def prepare(*args):
            callback_attempts['cleanup'] += 1
            return original_prepare(*args)

        def choose(*args):
            callback_attempts['attach'] += 1
            return choose_recorded_episode(*args)

        monkeypatch.setattr(client, 'transaction', transaction)
        monkeypatch.setattr(episode_empty_members, 'prepare', prepare)

        def cleanup():
            barrier.wait(timeout=90)
            return recording_sessions.tombstone_and_delete_empty_conversation(
                uid,
                'stub',
                'session',
                firestore_client=client,
            )

        def reconnect():
            barrier.wait(timeout=90)
            return attach('next', 62, choose)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='cleanup-attach') as pool:
            deletion = pool.submit(cleanup)
            attachment = pool.submit(reconnect)
            assert deletion.result(timeout=90)
            assert attachment.result(timeout=90)['id'] == owner
        # Both calls committed under run_transactional's existing three fresh
        # transactions, each with at most five SDK commit attempts.
        assert len(transactions) == 2 and all(count <= 3 for count in transactions.values()), transactions
        assert all(1 <= count <= 15 for count in callback_attempts.values()), callback_attempts
        final = root.collection('episodes').document(owner).get().to_dict()
        assert set(final['conversation_ids']) == ({'speech', 'next'} if enabled else {'speech', 'stub', 'next'})
        assert final['state_version'] == initial + (2 if enabled else 1)
        assert not conversation.get().exists
        assert root.collection('episode_links').document('next').get().to_dict()['episode_id'] == owner
        print(f'cleanup_enabled={enabled} transactions={transactions} callbacks={callback_attempts}')
    finally:
        client.close()
