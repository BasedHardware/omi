"""Regression: an app-posted chat message must be linked to that app's chat session.

database.chat.add_app_message stored the message without a chat_session_id and never called
add_message_to_chat_session. get_messages filters by chat_session_id whenever a session exists
(database/chat.py, session-scoped branch) and a Firestore equality filter never matches a null
field, so the message was stored but never returned on that path: the push notification fires and
deep-links into the app's chat, which opens without the message.

The sibling add_integration_chat_message, ten lines below, already does all three steps and its
docstring states the requirement: "linking it to the user's existing chat session so it appears in
the chat feed". This makes add_app_message agree with it.

Seam: monkeypatch.setattr on database.chat module attributes; no sys.modules mutation and no
Firestore client construction.
"""

import database.chat as chat_db


def _capture(monkeypatch, session):
    """Patch the three collaborators and return (stored_message, session_links)."""
    stored: dict = {}
    links: list = []

    monkeypatch.setattr(chat_db, 'get_chat_session', lambda uid, app_id=None: session)
    monkeypatch.setattr(chat_db, 'add_message', lambda uid, data: stored.update(data))
    monkeypatch.setattr(
        chat_db,
        'add_message_to_chat_session',
        lambda uid, session_id, message_id: links.append((session_id, message_id)),
    )
    return stored, links


def test_app_message_is_linked_to_the_apps_chat_session(monkeypatch):
    stored, links = _capture(monkeypatch, {'id': 'sess-1'})

    message = chat_db.add_app_message('hello', 'app-1', 'uid-1')

    # Without these the message is invisible to the session-scoped read in get_messages.
    assert stored['chat_session_id'] == 'sess-1'
    assert links == [('sess-1', message.id)]


def test_app_message_without_a_session_is_unchanged(monkeypatch):
    # No session yet: the message still stores, and nothing is linked. get_messages falls back to
    # its plugin_id branch in that case, which already worked.
    stored, links = _capture(monkeypatch, None)

    message = chat_db.add_app_message('hello', 'app-1', 'uid-1')

    assert stored['chat_session_id'] is None
    assert links == []
    assert message.app_id == 'app-1'


def test_conversation_id_is_still_recorded(monkeypatch):
    stored, _links = _capture(monkeypatch, {'id': 'sess-1'})

    chat_db.add_app_message('hello', 'app-1', 'uid-1', conversation_id='conv-9')

    assert stored['memories_id'] == ['conv-9']
