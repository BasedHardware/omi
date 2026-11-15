"""Empty-live deletion and episode detachment share a real loopback transaction."""

import os
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import episode_empty_members, recording_sessions

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
        assert link.get().exists is (audio or not enabled)
        assert stored['conversation_ids'] == (['speech'] if enabled and not audio else ['speech', 'empty'])
        assert session.get().to_dict()['lifecycle_phase'] == ('in_progress' if audio else 'discarded')
        if enabled and not audio:
            assert stored['state_version'] == 4
            assert stored['home_needs_prepare'] is True
            assert stored['recorded_members'] == {'speech': {}}
    finally:
        client.close()
