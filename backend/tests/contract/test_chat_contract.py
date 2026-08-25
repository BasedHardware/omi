"""Dual-backend contract for chat reads and writes (ADR-0044 facade + ADR-0002 store port).

`database/chat.py` is the single densest concentration of query shapes the facade has to *translate*
rather than pass through — the coverage inventory (ADR-0060) scores it 6 of 8, more than any other
domain module:

    aggregation       get_message_count: bare .count() and .count() behind a filter
    cursor            get_messages_reconcile_page: start_after(<document snapshot>)
    projection        get_chats_to_migrate: .select(['data_protection_level'])
    atomic_field_ops  save_message: Increment(1); delete_messages: ArrayRemove + Increment(-n)
    batch             delete_messages / add_multi_files: db.batch() spanning TWO collections
    transaction       _apply_existing_message_revision: get(transaction=...) under @transactional

and it carries a write precondition (`db.write_option(last_update_time=...)`) whose whole purpose is
to make a concurrent mutation fail loudly. None of that had dual-backend cover: the unit suites drive
chat.py through the in-memory fake, which implements the sentinels in Python and cannot disagree with
itself, and the live E2E never counts, pages or clears a chat.

Runs the real chain — chat.py -> the client each posture deploys -> live backend — against a Firestore
emulator and a real Mongo replica set, and asserts the two agree. Binding and skip rules: the shared
``bind_store`` fixture in ``conftest.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def chat(bind_store):
    """A user with one chat session and four messages, one of them reported.

    Ids are unique per run, and every seeded path is torn down: the contract suites share one live
    Firestore emulator and one live Mongo database, so a leaked document is a cross-test failure in
    whichever suite runs next.
    """
    import database.chat as chat_db

    run = uuid.uuid4().hex[:8]
    uid = f"chat-{run}"
    session_id = f"sess-{run}"
    message_ids = [f"m{i}-{run}" for i in range(4)]
    paths = [f"users/{uid}/chat_sessions/{session_id}"] + [f"users/{uid}/messages/{mid}" for mid in message_ids]

    bind_store.set(
        f"users/{uid}/chat_sessions/{session_id}",
        {
            "id": session_id,
            "title": "New Chat",
            "preview": "message 3",
            "created_at": BASE,
            "updated_at": BASE,
            "app_id": None,
            "plugin_id": None,
            "message_count": 4,
            "message_ids": list(message_ids),
            "starred": False,
        },
    )
    for index, message_id in enumerate(message_ids):
        bind_store.set(
            f"users/{uid}/messages/{message_id}",
            {
                "id": message_id,
                "text": f"message {index}",
                "sender": "human",
                "created_at": BASE + timedelta(minutes=index),
                "plugin_id": None,
                "chat_session_id": session_id,
                "type": "text",
                # message 1 is reported: every chat view hides it, so the count must exclude it too.
                "reported": index == 1,
                # 'standard' keeps the seeded text in the clear; 'enhanced' would demand a matching
                # per-uid encryption of every field, which is not what this suite is about.
                "data_protection_level": "standard",
            },
        )
    yield chat_db, uid, session_id, message_ids
    for path in paths:
        bind_store.delete(path)


def test_message_count_aggregates_and_excludes_reported(chat):
    """`.count()` bare and `.count()` behind a filter — total minus the reported subset."""
    chat_db, uid, _session_id, _message_ids = chat
    assert chat_db.get_message_count(uid) == 3


def test_message_count_of_an_empty_chat_is_zero(chat):
    """An aggregation over an empty collection must be 0, not an error or a missing result row."""
    chat_db, _uid, _session_id, _message_ids = chat
    assert chat_db.get_message_count(f"nobody-{uuid.uuid4().hex[:8]}") == 0


def test_reconcile_page_walks_a_document_cursor_without_gaps_or_repeats(chat):
    """`start_after(<snapshot>)`: the keyset page the desktop journal depends on.

    Newest first, reported rows scanned but withheld. Paging with limit=1 must therefore visit
    messages 3, 2, 0 — never 1, and never the same row twice.
    """
    chat_db, uid, session_id, message_ids = chat
    seen, cursor = [], None
    for _ in range(3):
        page, cursor, _has_more = chat_db.get_messages_reconcile_page(
            uid, limit=1, cursor_message_id=cursor, chat_session_id=session_id
        )
        seen.extend(message["id"] for message in page)
    assert seen == [message_ids[3], message_ids[2], message_ids[0]]

    tail, _cursor, has_more = chat_db.get_messages_reconcile_page(
        uid, limit=1, cursor_message_id=cursor, chat_session_id=session_id
    )
    assert tail == [] and has_more is False


def test_a_cursor_outside_the_scope_is_rejected_not_silently_ignored(chat):
    """The cursor is validated by re-reading the document — a read the adapter must honor."""
    chat_db, uid, session_id, message_ids = chat
    with pytest.raises(chat_db.MessageReconcileCursorError):
        chat_db.get_messages_reconcile_page(
            uid, limit=1, cursor_message_id=message_ids[0], chat_session_id=f"other-{session_id}"
        )
    with pytest.raises(chat_db.MessageReconcileCursorError):
        chat_db.get_messages_reconcile_page(uid, limit=1, cursor_message_id="does-not-exist")


def test_get_chats_to_migrate_projects_a_single_field(chat):
    """`.select(['data_protection_level'])`: the projection must still yield every document id.

    A projection that drops documents (or returns full payloads) both pass a naive assertion, so this
    checks the ids AND that the level actually read back is the seeded one.
    """
    chat_db, uid, _session_id, message_ids = chat
    to_enhanced = chat_db.get_chats_to_migrate(uid, 'enhanced')
    assert {row["id"] for row in to_enhanced} == set(message_ids)
    assert all(row["type"] == "chat" for row in to_enhanced)
    # Seeded level IS 'standard', so nothing is pending a migration to it.
    assert chat_db.get_chats_to_migrate(uid, 'standard') == []


def test_save_message_increments_the_session_counter(chat, bind_store):
    """`Increment(1)` on another collection's document, plus the preview write."""
    chat_db, uid, session_id, _message_ids = chat
    result = chat_db.save_message(uid, "a new message", "human", session_id=session_id)
    assert result["created"] is True
    session = bind_store.get(f"users/{uid}/chat_sessions/{session_id}").data
    assert session["message_count"] == 5
    assert session["preview"] == "a new message"
    bind_store.delete(f"users/{uid}/messages/{result['id']}")


def test_a_replayed_client_message_id_does_not_bump_the_counter(chat, bind_store):
    """The idempotency path runs `get(transaction=...)` under `@transactional`.

    Its product invariant is that a retried save is a no-op on the counter — which is exactly what a
    transaction whose read escaped the session would get wrong.
    """
    chat_db, uid, session_id, _message_ids = chat
    client_message_id = f"cmid-{uuid.uuid4().hex[:8]}"
    first = chat_db.save_message(uid, "retried", "human", session_id=session_id, client_message_id=client_message_id)
    second = chat_db.save_message(uid, "retried", "human", session_id=session_id, client_message_id=client_message_id)
    assert first["created"] is True and second["created"] is False
    assert first["id"] == second["id"] == client_message_id
    session = bind_store.get(f"users/{uid}/chat_sessions/{session_id}").data
    assert session["message_count"] == 5, "a replay must not double-count"
    bind_store.delete(f"users/{uid}/messages/{client_message_id}")


def test_a_conflicting_payload_under_the_same_client_message_id_is_refused(chat, bind_store):
    """Same id, different text: the transactional arbitration must reject it on both backends."""
    chat_db, uid, session_id, _message_ids = chat
    client_message_id = f"cmid-{uuid.uuid4().hex[:8]}"
    chat_db.save_message(uid, "original", "human", session_id=session_id, client_message_id=client_message_id)
    with pytest.raises(chat_db.ClientMessageIdPayloadConflict):
        chat_db.save_message(uid, "different", "human", session_id=session_id, client_message_id=client_message_id)
    bind_store.delete(f"users/{uid}/messages/{client_message_id}")


def test_delete_messages_applies_the_inverse_session_updates(chat, bind_store):
    """The batch that spans two collections: message deletes + ArrayRemove/Increment on the session.

    Asserts the *whole* inverse, because a partially-applied batch is the failure mode that matters:
    messages gone but the counter left behind is permanent, user-visible counter drift.
    """
    chat_db, uid, session_id, message_ids = chat
    assert chat_db.delete_messages(uid, session_id=session_id) == 4
    assert chat_db.get_messages(uid, chat_session_id=session_id) == []
    session = bind_store.get(f"users/{uid}/chat_sessions/{session_id}").data
    assert session["message_count"] == 0, "counter left behind -> permanent drift"
    assert session["message_ids"] == [], f"ArrayRemove did not remove {message_ids}"
    assert session["preview"] is None, "the preview pointed at a message that no longer exists"


def test_delete_messages_is_scoped_and_returns_zero_when_nothing_matches(chat, bind_store):
    """An empty match must not touch the session document at all."""
    chat_db, uid, session_id, _message_ids = chat
    assert chat_db.delete_messages(uid, session_id=f"other-{session_id}") == 0
    session = bind_store.get(f"users/{uid}/chat_sessions/{session_id}").data
    assert session["message_count"] == 4 and session["preview"] == "message 3"


def test_a_stale_write_precondition_fails_loudly(chat, bind_store):
    """`db.write_option(last_update_time=...)` exists to make a lost update impossible.

    A precondition the adapter ignored would let the write land — silently reintroducing the race the
    caller's retry loop was written to detect. Driven through the facade the way chat.py does.
    """
    from google.api_core.exceptions import FailedPrecondition

    from database._client import db

    chat_db, uid, session_id, _message_ids = chat
    del chat_db
    session_ref = db.collection('users').document(uid).collection('chat_sessions').document(session_id)
    snapshot = session_ref.get()
    assert snapshot.exists

    # Somebody else writes: the revision the snapshot captured is now stale.
    bind_store.update(f"users/{uid}/chat_sessions/{session_id}", {"title": "renamed by a racer"})

    batch = db.batch()
    batch.update(
        session_ref, {"title": "based on a stale read"}, option=db.write_option(last_update_time=snapshot.update_time)
    )
    with pytest.raises(FailedPrecondition):
        batch.commit()
    assert bind_store.get(f"users/{uid}/chat_sessions/{session_id}").data["title"] == "renamed by a racer"
