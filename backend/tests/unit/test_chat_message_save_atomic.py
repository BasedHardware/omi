"""Initial saves stage the message and its session projection in one transaction.

The shared fixture proves write shape and read-before-write ordering only.
Rollback, real Increment arithmetic, create collisions and retries are covered
by test_chat_message_save_atomic_emulator.py, not by this in-memory fixture.
"""

import pytest

from database import chat
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

SESSION = ('users', 'synthetic-uid', 'chat_sessions', 'synthetic-session')


@pytest.mark.parametrize('keyed', [False, True])
@pytest.mark.parametrize('session_exists', [False, True])
@pytest.mark.parametrize('text', ['', 'x' * 200])
def test_new_message_and_existing_session_share_one_read_before_write_transaction(keyed, session_exists, text):
    store = StrictFirestore({SESSION: {'message_count': 0}} if session_exists else {})
    result = chat.save_message(
        'synthetic-uid',
        text=text,
        sender='ai',
        app_id='synthetic-app',
        session_id='synthetic-session',
        metadata='{"synthetic":true}',
        content_blocks=[{'type': 'text', 'text': text}],
        client_message_id='synthetic-turn' if keyed else None,
        journal_revision=4 if keyed else None,
        firestore_client=store,
    )
    assert result['created'] is True
    assert len(store.transactions) == 1
    transaction = store.transactions[0]
    writes = transaction.creates if keyed else transaction.sets
    assert len(writes) == 1
    assert (transaction.sets if keyed else transaction.creates) == []
    path, message = writes[0]
    assert path == ('users', 'synthetic-uid', 'messages', result['id'])
    assert message['chat_session_id'] == message['session_id'] == result['session_id'] == 'synthetic-session'
    assert message['plugin_id'] == message['app_id'] == 'synthetic-app'
    assert message['metadata'] == '{"synthetic":true}'
    assert message['content_blocks'] == [{'type': 'text', 'text': text}]
    assert message['type'] == 'text' and message['from_external_integration'] is False
    if session_exists:
        assert len(transaction.updates) == 1
        session_path, patch = transaction.updates[0]
        assert session_path == SESSION
        assert patch['message_count'].value == 1
        assert patch['preview'] == (text[:100] if text else None)
        assert patch['updated_at'] == message['created_at']
    else:
        assert transaction.updates == []
        assert SESSION not in store.rows


def test_idempotent_replay_does_not_stage_another_message_or_counter_increment():
    store = StrictFirestore({SESSION: {'message_count': 0}})
    args = dict(
        text='hello',
        sender='ai',
        session_id='synthetic-session',
        client_message_id='synthetic-turn',
        firestore_client=store,
    )
    first = chat.save_message('synthetic-uid', **args)
    retry = chat.save_message('synthetic-uid', **args)
    assert first['created'] is True and retry['created'] is False
    assert retry['id'] == first['id']
    assert len(store.transactions) == 2
    assert store.transactions[1].creates == store.transactions[1].sets == store.transactions[1].updates == []


def test_auto_acquired_session_does_not_replace_requested_identity(monkeypatch):
    store = StrictFirestore({SESSION: {'message_count': 0}})
    acquired = []
    monkeypatch.setattr(
        chat, 'acquire_chat_session', lambda *args, **kwargs: acquired.append(True) or 'synthetic-session'
    )
    args = dict(text='hello', sender='ai', client_message_id='synthetic-turn', firestore_client=store)
    first = chat.save_message('synthetic-uid', **args)
    replay = chat.save_message('synthetic-uid', **args)
    assert acquired == [True]
    assert replay['session_id'] == first['session_id'] == 'synthetic-session'
    assert replay['created'] is False
    with pytest.raises(chat.ClientMessageIdPayloadConflict):
        chat.save_message('synthetic-uid', session_id='synthetic-session', **args)
