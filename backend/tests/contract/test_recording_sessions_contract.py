"""Dual-backend contract for recording sessions (ADR-0044 facade + ADR-0002 store port).

`database/recording_sessions.py` is the durable identity of one live recording: which conversation it
writes into, and how far along its lifecycle it has got. The client reconnects, retries, and races its
own uploads, so every entry point in the module is one shape:

    transaction   three read-modify-writes, each with its own user-visible failure.

                  (a) `create_or_get_recording_session` reads the session inside the transaction and
                  binds it to exactly ONE conversation id. A reconnecting client proposes a fresh id;
                  the server must hand back the id it already owns and flag the conflict. Without the
                  read the rebind is silent, and the second half of a recording is written into a
                  different conversation from the first — the user sees their meeting split in two,
                  with no error and no way to rejoin them.

                  (b) `record_lifecycle_event` reads the current phase and sequence and refuses to go
                  backwards, refuses to reopen a terminal phase, and does not advance the sequence for
                  a re-delivered event. The sequence is the client's ordering key. A write that skipped
                  the read would let a delayed `in_progress` frame arrive after `completed` and pull a
                  finished conversation back into the recording UI; a duplicate event would bump the
                  sequence and make the client see a gap it treats as a lost update.

                  (c) `tombstone_and_delete_empty_conversation` reads the conversation and DELETES it
                  only if it is still empty, terminalizing the bound session in the same transaction.
                  The module's own comment says what the transaction is for: segment and photo writes
                  set `has_content` on this same document, so the read must be part of the commit. If
                  it is not, cleanup deletes a conversation whose audio landed a moment later — that is
                  user data destroyed, silently, by a background sweep.

There is no batch, cursor, projection or aggregation here; the module is deliberately narrow (routing
metadata only, never transcript text), so this suite covers the one shape it has and no more.

Environment: importing this module pulls `database.conversations`, which requires `ENCRYPTION_SECRET`
to be set at import time. The committed run recipe already exports one.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def recording(bind_store):
    """One user, one recording session id, one proposed conversation id — none of them written yet."""
    run = uuid.uuid4().hex[:8]
    uid = f'rec-sess-{run}'

    yield {
        'uid': uid,
        'run': run,
        'session_id': f'rs-{run}',
        'conversation_id': f'conv-{run}',
        'store': bind_store,
    }

    for collection in ('recording_sessions', 'conversations'):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _session(recording, session_id: str | None = None):
    path = f"users/{recording['uid']}/recording_sessions/{session_id or recording['session_id']}"
    document = recording['store'].get(path)
    return document.data if document is not None and document.exists else None


def _conversation(recording, conversation_id: str | None = None):
    path = f"users/{recording['uid']}/conversations/{conversation_id or recording['conversation_id']}"
    document = recording['store'].get(path)
    return document.data if document is not None and document.exists else None


def _seed_conversation(recording, **overrides) -> str:
    """A live conversation row the way the listen path leaves one: in progress and empty."""
    conversation_id = overrides.pop('conversation_id', recording['conversation_id'])
    data = {
        'id': conversation_id,
        'status': 'in_progress',
        'created_at': NOW,
        'discarded': False,
        'transcript_segments': [],
    }
    data.update(overrides)
    recording['store'].set(f"users/{recording['uid']}/conversations/{conversation_id}", data)
    return conversation_id


# --- transaction: binding one recording to one conversation -------------------------------------------


def test_the_first_bind_creates_the_session_at_sequence_zero(recording):
    import database.recording_sessions as sessions_db

    binding = sessions_db.create_or_get_recording_session(
        recording['uid'], recording['session_id'], recording['conversation_id']
    )

    assert binding['conversation_id'] == recording['conversation_id']
    assert binding['lifecycle_phase'] == 'in_progress'
    assert binding['lifecycle_sequence'] == 0
    assert binding['mapping_conflict'] is False
    assert _session(recording)['uid'] == recording['uid'], 'the session document was never written'
    assert sessions_db.get_recording_session(recording['uid'], recording['session_id']) is not None
    assert sessions_db.get_recording_session(recording['uid'], f"absent-{recording['session_id']}") is None


def test_a_reconnecting_client_proposing_a_new_conversation_does_not_rebind_the_session(recording):
    """What the in-transaction read is FOR, and the only way to see it.

    The client dropped its socket, minted a fresh conversation id and reconnected with the SAME
    recording session id. The server must keep the binding it already has and say so. Asserting "one
    document under one id" would pass for a blind overwrite too, so what is asserted here is which
    conversation id survived — the one the first half of the audio went into.
    """
    import database.recording_sessions as sessions_db

    sessions_db.create_or_get_recording_session(recording['uid'], recording['session_id'], recording['conversation_id'])

    rebound = sessions_db.create_or_get_recording_session(
        recording['uid'], recording['session_id'], f"other-{recording['run']}"
    )

    assert rebound['conversation_id'] == recording['conversation_id'], 'the recording was re-pointed mid-flight'
    assert rebound['mapping_conflict'] is True, 'the caller was not told its proposal was rejected'
    assert _session(recording)['conversation_id'] == recording['conversation_id']


def test_re_proposing_the_same_conversation_is_idempotent(recording):
    """A plain retry of the bind — the common case on a flaky link. It must not report a conflict and
    must not disturb the lifecycle the recording has already reached."""
    import database.recording_sessions as sessions_db

    sessions_db.create_or_get_recording_session(recording['uid'], recording['session_id'], recording['conversation_id'])
    sessions_db.record_lifecycle_event(
        recording['uid'], recording['session_id'], recording['conversation_id'], 'processing'
    )

    again = sessions_db.create_or_get_recording_session(
        recording['uid'], recording['session_id'], recording['conversation_id']
    )

    assert again['mapping_conflict'] is False
    assert again['lifecycle_phase'] == 'processing', 'the re-bind reset the lifecycle it read'
    assert again['lifecycle_sequence'] == 1


def test_a_session_document_belonging_to_someone_else_is_refused(recording):
    """The identity check inside the transaction. Returning the binding anyway would route one user's
    recording into another user's conversation."""
    import database.recording_sessions as sessions_db

    recording['store'].set(
        f"users/{recording['uid']}/recording_sessions/{recording['session_id']}",
        {
            'uid': f"someone-else-{recording['run']}",
            'recording_session_id': recording['session_id'],
            'conversation_id': recording['conversation_id'],
        },
    )

    with pytest.raises(ValueError):
        sessions_db.create_or_get_recording_session(
            recording['uid'], recording['session_id'], recording['conversation_id']
        )
    with pytest.raises(ValueError):
        sessions_db.get_recording_session(recording['uid'], recording['session_id'])


# --- transaction: the monotonic lifecycle envelope ----------------------------------------------------


@pytest.fixture
def bound(recording):
    import database.recording_sessions as sessions_db

    sessions_db.create_or_get_recording_session(recording['uid'], recording['session_id'], recording['conversation_id'])
    return recording


def _event(bound, phase: str, conversation_id: str | None = None):
    import database.recording_sessions as sessions_db

    return sessions_db.record_lifecycle_event(
        bound['uid'], bound['session_id'], conversation_id or bound['conversation_id'], phase
    )


def test_the_lifecycle_advances_with_a_strictly_increasing_sequence(bound):
    """The sequence is the client's ordering key for the events it receives out of band."""
    processing = _event(bound, 'processing')
    completed = _event(bound, 'completed')

    assert (processing['accepted'], processing['lifecycle_sequence']) == (True, 1)
    assert (completed['accepted'], completed['lifecycle_sequence']) == (True, 2)
    assert _session(bound)['lifecycle_phase'] == 'completed'
    assert _session(bound)['lifecycle_sequence'] == 2


def test_a_re_delivered_event_is_accepted_without_advancing_the_sequence(bound):
    """A duplicate delivery is not new information. Bumping the sequence for it would make the client
    believe it missed an event and re-fetch state it already has."""
    _event(bound, 'processing')

    repeat = _event(bound, 'processing')

    assert repeat['accepted'] is True
    assert repeat['lifecycle_sequence'] == 1, 'a duplicate event advanced the sequence'
    assert _session(bound)['lifecycle_sequence'] == 1


def test_an_event_that_arrives_late_cannot_pull_the_recording_backwards(bound):
    """A delayed `in_progress` frame after `processing`. Accepting it would put a conversation that is
    already being transcribed back into the recording state in the UI."""
    _event(bound, 'processing')

    stale = _event(bound, 'in_progress')

    assert stale['accepted'] is False
    assert stale['discard_reason'] == 'stale_event'
    assert stale['lifecycle_phase'] == 'processing', 'the caller was told the wrong current phase'
    assert _session(bound)['lifecycle_phase'] == 'processing'
    assert _session(bound)['lifecycle_sequence'] == 1


def test_a_terminal_recording_is_immutable(bound):
    """`completed`, `failed` and `discarded` are the end. A later `failed` must not overwrite a
    `completed` recording, or a finished conversation reports as broken."""
    _event(bound, 'completed')

    late_failure = _event(bound, 'failed')

    assert late_failure['accepted'] is False
    assert late_failure['discard_reason'] == 'terminal_immutable'
    assert _session(bound)['lifecycle_phase'] == 'completed'
    assert _session(bound)['lifecycle_sequence'] == 1


def test_an_event_for_a_conversation_this_session_is_not_bound_to_is_discarded(bound):
    """The event names a conversation the session does not own — a client that reconnected with a new
    id, exactly the case the bind rejected. It must be dropped, and the reply must carry the id the
    server actually owns so the client can resynchronise."""
    misbound = _event(bound, 'completed', conversation_id=f"other-{bound['run']}")

    assert misbound['accepted'] is False
    assert misbound['discard_reason'] == 'mapping_conflict'
    assert misbound['conversation_id'] == bound['conversation_id']
    assert _session(bound)['lifecycle_phase'] == 'in_progress', 'a misbound event still moved the session'


def test_an_event_for_a_session_that_was_never_bound_creates_nothing(recording):
    """No document, no implicit creation: a lifecycle event must never mint a session, or a stray frame
    from an old client conjures a recording the user never started."""
    ghost = f"ghost-{recording['run']}"
    import database.recording_sessions as sessions_db

    event = sessions_db.record_lifecycle_event(recording['uid'], ghost, recording['conversation_id'], 'completed')

    assert event['accepted'] is False
    assert event['discard_reason'] == 'missing_session'
    assert _session(recording, ghost) is None


# --- transaction: deleting an empty conversation ------------------------------------------------------


def test_an_empty_live_conversation_is_deleted_and_its_session_terminalized(bound):
    """Both writes are one commit: the row goes and the session it was bound to becomes `discarded`, so
    nothing later tries to deliver events into a conversation that no longer exists."""
    import database.recording_sessions as sessions_db

    _seed_conversation(bound)

    assert (
        sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], bound['conversation_id'], bound['session_id'])
        is True
    )

    assert _conversation(bound) is None
    assert _session(bound)['lifecycle_phase'] == 'discarded'
    assert _session(bound)['lifecycle_sequence'] == 1, 'the tombstone must be an ordered lifecycle event'


def test_a_conversation_whose_audio_landed_is_never_deleted(bound):
    """The reason the read is inside the transaction, stated in the module's own comment: a segment
    write sets `has_content` on this same document. Cleanup must see it. Deleting here is destroying a
    recording the user made."""
    import database.recording_sessions as sessions_db

    _seed_conversation(bound, has_content=True)

    assert (
        sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], bound['conversation_id'], bound['session_id'])
        is False
    )

    assert _conversation(bound) is not None, 'a conversation with content was deleted'
    assert _session(bound)['lifecycle_phase'] == 'in_progress', 'the session was terminalized anyway'
    assert _session(bound)['lifecycle_sequence'] == 0


def test_a_conversation_holding_transcript_or_photos_is_never_deleted(bound):
    """The other two ways a conversation is non-empty. `transcript_segments` is decoded rather than
    length-checked, because it is stored compressed and an empty list is a non-empty blob."""
    import database.recording_sessions as sessions_db

    with_photos = _seed_conversation(bound, conversation_id=f"photo-{bound['run']}", photos=[{'id': 'p1'}])
    with_speech = _seed_conversation(
        bound, conversation_id=f"speech-{bound['run']}", transcript_segments=[{'text': 'hello', 'speaker': 'SPEAKER_0'}]
    )

    assert sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], with_photos, None) is False
    assert sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], with_speech, None) is False

    assert _conversation(bound, with_photos) is not None
    assert _conversation(bound, with_speech) is not None


def test_a_conversation_that_has_moved_past_recording_is_left_alone(bound):
    """Only `in_progress` rows are cleanup candidates. A conversation already being processed, or one
    the user discarded themselves, is owned by another path."""
    import database.recording_sessions as sessions_db

    processing = _seed_conversation(bound, conversation_id=f"proc-{bound['run']}", status='processing')
    discarded = _seed_conversation(bound, conversation_id=f"disc-{bound['run']}", discarded=True)

    assert sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], processing, None) is False
    assert sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], discarded, None) is False

    assert _conversation(bound, processing) is not None
    assert _conversation(bound, discarded) is not None


def test_a_conversation_that_is_already_gone_reports_nothing_to_do(bound):
    """Cleanup runs more than once for the same recording; the second run must be a quiet False rather
    than an error that fails the socket teardown."""
    import database.recording_sessions as sessions_db

    assert (
        sessions_db.tombstone_and_delete_empty_conversation(
            bound['uid'], f"never-existed-{bound['run']}", bound['session_id']
        )
        is False
    )


def test_a_session_bound_to_a_different_conversation_is_not_terminalized_by_the_cleanup(bound):
    """The deletion and the terminalization are independent decisions inside the same transaction. The
    empty row still goes, but a session that is recording something else must keep running."""
    import database.recording_sessions as sessions_db

    orphan = _seed_conversation(bound, conversation_id=f"orphan-{bound['run']}")

    assert sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], orphan, bound['session_id']) is True

    assert _conversation(bound, orphan) is None
    assert _session(bound)['lifecycle_phase'] == 'in_progress', 'an unrelated live recording was discarded'
    assert _session(bound)['lifecycle_sequence'] == 0


def test_an_already_terminal_session_is_not_moved_again_by_the_cleanup(bound):
    """A session that already reported `completed` keeps its phase and its sequence; only the empty
    conversation row is removed."""
    import database.recording_sessions as sessions_db

    _seed_conversation(bound)
    _event(bound, 'completed')

    assert (
        sessions_db.tombstone_and_delete_empty_conversation(bound['uid'], bound['conversation_id'], bound['session_id'])
        is True
    )

    assert _conversation(bound) is None
    assert _session(bound)['lifecycle_phase'] == 'completed'
    assert _session(bound)['lifecycle_sequence'] == 1, 'a terminal session was re-sequenced'
