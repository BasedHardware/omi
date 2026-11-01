"""Loopback-only transactions, source paging, summary invalidation and per-turn usage."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.messaging import MessagingStore
from database.chat_context import ChatContextStore
from database import chat as chat_db
from database.llm_usage import record_llm_usage


@pytest.fixture
def store():
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Local Firestore emulator not requested')
    assert host.startswith('127.0.0.1:')
    os.environ['FIRESTORE_EMULATOR_HOST'] = host
    client = firestore.Client(project='demo-context-' + uuid4().hex[:10], credentials=AnonymousCredentials())
    messaging = MessagingStore(firestore_client=client)
    messaging.user('u').set({'subscription': {'plan': 'operator'}})
    messaging.user('u').collection('chat_sessions').document('s').set({'id': 's'})
    for i in range(25):
        messaging.user('u').collection('messages').document(str(i)).set(
            {
                'id': str(i),
                'chat_session_id': 's',
                'plugin_id': None,
                'text': 'message ' + str(i),
                'sender': 'human' if i % 2 == 0 else 'ai',
                'created_at': datetime(2026, 10, 14, tzinfo=timezone.utc) + timedelta(seconds=i),
            }
        )
    yield ChatContextStore(messaging=messaging)
    client.close()


def test_scoped_source_pages_and_encrypted_state_compare_and_swap(store):
    rows, cursor, more = store.source_page('u', 's', '20', limit=8)
    assert len(rows) == 8 and cursor['id'] == '7' and more
    rows2, cursor2, more = store.source_page('u', 's', '20', cursor, limit=40)
    assert len(rows2) == 12 and cursor2['id'] == '19' and not more
    state = store.load('u', 's')
    state['summary'] = 'private continuity'
    store.save('u', 's', state, 0)
    raw = store.messaging.user('u').collection('chat_sessions').document('s').get().to_dict()
    assert 'private continuity' not in raw['shaped_context']
    assert store.load('u', 's')['summary'] == 'private continuity'
    with pytest.raises(RuntimeError, match='Concurrent'):
        store.save('u', 's', state, 0)
    with pytest.raises(PermissionError):
        store.source_page('other', 's', '20')
    with pytest.raises(PermissionError):
        store.source_page('u', 'other-session', '20')


def test_reporting_invalidates_summary_and_fences_old_writer(store, monkeypatch):
    state = store.load('u', 's')
    store.save('u', 's', dict(state, summary='removed fact'), 0)
    old = store.load('u', 's')
    monkeypatch.setattr(chat_db, 'db', store.messaging.db)
    assert chat_db.report_message('u', '1') == {'message': 'Message reported'}
    assert 'shaped_context' not in store.messaging.user('u').collection('chat_sessions').document('s').get().to_dict()
    fresh = store.load('u', 's')
    assert 'summary' not in fresh and fresh['generation'] == 1
    with pytest.raises(PermissionError, match='changed'):
        store.save('u', 's', old, old['revision'])
    rows, _, _ = store.source_page('u', 's', '5')
    assert all(row['content'] != 'message 1' for row in rows)


def test_session_removal_prevents_context_resurrection(store):
    state = store.load('u', 's')
    store.messaging.user('u').collection('chat_sessions').document('s').delete()
    with pytest.raises(PermissionError):
        store.save('u', 's', dict(state, summary='secret'), 0)
    with pytest.raises(PermissionError):
        store.load('u', 's')
    assert not store.messaging.user('u').collection('chat_sessions').document('s').get().exists


def test_usage_aggregates_cache_and_surface_and_audits_each_turn(store):
    for _ in range(2):
        record_llm_usage(
            'u',
            'chat_agent',
            'gpt-5.6',
            1200,
            40,
            cache_read_tokens=800,
            cache_write_tokens=100,
            surface='telegram',
            turn_id='turn-one',
            firestore_client=store.messaging.db,
        )
    record_llm_usage(
        'u',
        'chat_agent',
        'gpt-5.6',
        1000,
        30,
        cache_read_tokens=500,
        cache_write_tokens=0,
        surface='app',
        turn_id='turn-two',
        firestore_client=store.messaging.db,
    )
    docs = list(store.messaging.user('u').collection('llm_usage').stream())
    row = docs[0].to_dict()
    assert row['chat_agent']['gpt-5_6']['input_tokens'] == 3400
    assert row['chat_agent']['gpt-5_6']['cache_read_tokens'] == 2100
    assert row['chat_agent']['gpt-5_6']['cache_write_tokens'] == 200
    assert row['chat_agent_surfaces']['telegram']['gpt-5_6']['call_count'] == 2
    assert row['chat_agent_surfaces']['app']['gpt-5_6']['call_count'] == 1
    turns = list(docs[0].reference.collection('chat_agent_turns').stream())
    assert len(turns) == 2
    telegram = next(d.to_dict() for d in turns if d.to_dict()['surface'] == 'telegram')
    assert telegram['models']['gpt-5_6']['input_tokens'] == 2400


def test_revoked_channel_and_removed_account_fence_summary_writes(store):
    session = store.messaging.user('u').collection('chat_sessions').document('s')
    identity = store.messaging.db.collection('channel_identities').document('link')
    identity.set({'active': True, 'uid': 'u', 'generation': 1})
    session.update({'channel_link_id': 'link', 'link_generation': 1})
    state = store.load('u', 's')
    identity.update({'active': False, 'generation': 2})
    with pytest.raises(PermissionError, match='revoked'):
        store.save('u', 's', dict(state, summary='secret'), 0)
    identity.update({'active': True, 'generation': 1})
    store.messaging.user('u').delete()
    with pytest.raises(PermissionError, match='Account'):
        store.save('u', 's', dict(state, summary='secret'), 0)


def test_new_channel_session_does_not_copy_derived_context(store):
    from types import SimpleNamespace
    from database.messaging import key

    message = SimpleNamespace(channel='telegram', external_chat_id='chat')
    ref = store.messaging.user('u').collection('chat_sessions').document(key('channel:' + key('telegram', 'chat')))
    ref.set({'id': ref.id, 'shaped_context': 'encrypted-old-summary', 'shaped_context_revision': 3})
    fresh = store.messaging.reset_session('u', message, {})
    assert 'shaped_context' not in fresh and 'shaped_context_revision' not in fresh
    assert ref.get().to_dict()['shaped_context'] == 'encrypted-old-summary'
    assert ref.get().to_dict()['current_session_id'] == fresh['id']


@pytest.mark.parametrize('mutation', ['clear', 'batch_delete', 'journal'])
def test_history_mutations_erase_summary_in_the_atomic_write(store, monkeypatch, mutation):
    state = store.load('u', 's')
    store.save('u', 's', dict(state, summary='Private old fact'), 0)
    stale = store.load('u', 's')
    monkeypatch.setattr(chat_db, 'db', store.messaging.db)
    if mutation == 'clear':
        assert chat_db.delete_messages('u', session_id='s') == 25
    elif mutation == 'batch_delete':
        chat_db.batch_delete_messages(store.messaging.user('u'), chat_session_id='s')
    else:
        store.messaging.user('u').collection('messages').document('1').update(
            {
                'message_source': 'desktop_chat',
                'journal_revision': 1,
                'metadata': None,
                'app_id': None,
                'plugin_id': None,
            }
        )
        result = chat_db.save_message(
            'u',
            text='Revised fact',
            sender='ai',
            session_id='s',
            client_message_id='1',
            journal_revision=2,
            firestore_client=store.messaging.db,
        )
        assert result['updated'] is True
    row = store.messaging.user('u').collection('chat_sessions').document('s').get().to_dict()
    assert 'shaped_context' not in row and row['shaped_context_revision'] > stale['revision']
    with pytest.raises(PermissionError, match='changed'):
        store.save('u', 's', stale, stale['revision'])


def test_app_auto_document_id_is_resolved_by_wire_id(store, monkeypatch):
    monkeypatch.setattr(chat_db, 'db', store.messaging.db)
    chat_db.add_message(
        'u',
        {
            'id': 'wire-anchor',
            'chat_session_id': 's',
            'text': 'Synthetic app turn',
            'sender': 'human',
            'plugin_id': None,
            'memories': [],
            'data_protection_level': 'standard',
            'created_at': datetime(2026, 10, 15, tzinfo=timezone.utc),
        },
    )
    # The original reader found no document here and raised PermissionError.
    assert not store.messaging.user('u').collection('messages').document('wire-anchor').get().exists
    rows, _, _ = store.source_page('u', 's', 'wire-anchor')
    assert len(rows) == 25
    with pytest.raises(PermissionError):
        store.source_page('u', 's', 'nonexistent')
    # A matching wire ID in a foreign session never grants continuity access.
    store.messaging.user('u').collection('messages').document('other').set(
        {
            'id': 'foreign',
            'chat_session_id': 'other',
            'created_at': datetime.now(timezone.utc),
        }
    )
    with pytest.raises(PermissionError, match='outside session'):
        store.source_page('u', 's', 'foreign')
