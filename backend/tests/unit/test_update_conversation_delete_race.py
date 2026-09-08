"""Regression test: update_conversation must honor its gone-owner contract when the
delete lands between its existence read and its commit.

Production loop sensor (pusher, latest 30-min windows) recorded a NEW error
signature immediately after the ``list_audio_chunks`` NameError class (fixed in
#12439) stopped firing:

    ERROR:routers.pusher:Error updating audio files: 404 No document to update:
    projects/based-hardware/databases/(default)/documents/users/<uid>/
    conversations/<conversation_id>

``database.conversations.update_conversation`` documents that it "Returns False
when the conversation no longer exists, so callers that keep producing work for
it (e.g. the pusher's private-cloud audio sync) can stop instead of writing
into a deleted owner", and the pusher's private-cloud flush builds its designed
gone-owner path on exactly that return value (stop syncing, add to
``deleted_conversations``, release the audio budget, record the drop
fallback). But the function implemented the check-then-act non-atomically:
``get()`` → ``update()`` with no transaction. A conversation deleted in between
(the same mid-session empty-generation delete #11860 defends against) makes
``update()`` raise ``google.api_core.exceptions.NotFound`` (404 No document to
update), which escapes to each caller's broad ``except Exception`` as an ERROR
log — so the designed gone-owner path never runs and the pusher session keeps
producing audio work for a conversation that no longer exists.

The suite never noticed because every existing test exercises the two
sequential states (exists → update; missing → False) — nothing deletes the
document *between* the read and the commit, which is the only interleaving the
contract is about.

These tests drive the real ``update_conversation`` through a controllable seam
(``conversations_db.db``), with a fake Firestore whose document can vanish
between ``get()`` and ``update()`` — the exact production race — and then drive
the two highest-volume affected callers (the pusher flush and the sync
finalizer) through their real code to prove they take their designed
gone-owner paths instead of logging ERROR, while genuine failures still log.

Failure-Class: new — the violated contract is ``update_conversation``'s own
documented gone-owner return: a delete racing the write must be reported as
False, not raised as NotFound. Instance fix at the authoritative owner (the
database layer), where every caller benefits without per-call-site exception
handling — the pattern AGENTS.md prescribes ("don't add another call-site
exception when ownership is the real problem").
"""

import asyncio
import logging
import struct
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from google.api_core.exceptions import NotFound
from starlette.websockets import WebSocketState

import database.conversations as conversations_db

UID = 'uid'
CONVERSATION_ID = 'conversation'
CONVERSATION_PATH = ('users', UID, 'conversations', CONVERSATION_ID)


# ---------------------------------------------------------------------------
# Fake Firestore with a controllable mid-flight delete — the production race.
# ---------------------------------------------------------------------------


class _RaceDocumentRef:
    """Document reference whose update() raises NotFound like real Firestore.

    Real Firestore ``update()`` on a missing document raises
    ``google.api_core.exceptions.NotFound("404 No document to update: ...")`` —
    the exact production message. ``get()`` may still see the snapshot if the
    delete commits after the read, which is the race window being tested.
    """

    def __init__(self, store: '_RaceFirestore', path: tuple):
        self._store = store
        self._path = path

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self._store, self._path + (name,))

    def get(self):
        documents = self._store.documents
        if self._path not in documents:
            return SimpleNamespace(exists=False, to_dict=lambda: None)
        data = deepcopy(documents[self._path])
        return SimpleNamespace(exists=True, to_dict=lambda: data)

    def update(self, updates: dict):
        documents = self._store.documents
        if self._path in self._store.delete_on_get:
            # The delete commits now: the document vanishes before this write
            # lands, exactly like the production race.
            documents.pop(self._path, None)
        if self._path not in documents:
            raise NotFound(f'404 No document to update: {"/".join(self._path)}')
        documents[self._path].update(deepcopy(updates))


class _CollectionRef:
    def __init__(self, store: '_RaceFirestore', path: tuple):
        self._store = store
        self._path = path

    def document(self, document_id: str) -> '_RaceDocumentRef':
        return _RaceDocumentRef(self._store, self._path + (document_id,))


class _RaceFirestore:
    """``conversations_db.db`` double that can delete mid-flight.

    ``delete_on_get`` holds the document paths that vanish between ``get()``
    and ``update()`` — the production race. The snapshot read still sees the
    document; the commit raises NotFound with the production message.
    """

    def __init__(self, documents: dict = None):
        self.documents = documents if documents is not None else {}
        self.delete_on_get: set = set()

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self, (name,))


def _fake_store(monkeypatch, **conversation) -> _RaceFirestore:
    store = _RaceFirestore({CONVERSATION_PATH: dict(conversation)})
    monkeypatch.setattr(conversations_db, 'db', store)
    return store


# ---------------------------------------------------------------------------
# The contract: a delete between read and commit is False, not NotFound.
# ---------------------------------------------------------------------------


def test_update_raced_by_delete_returns_false_instead_of_raising(monkeypatch):
    """Before the fix this raised NotFound('404 No document to update').

    The document exists at the existence read and is gone at the commit —
    the exact interleaving the gone-owner contract governs.
    """
    store = _fake_store(monkeypatch, data_protection_level='standard', language='en')
    store.delete_on_get.add(CONVERSATION_PATH)

    result = conversations_db.update_conversation(UID, CONVERSATION_ID, {'language': 'fr'})

    assert result is False


def test_update_missing_document_returns_false(monkeypatch):
    """Control: a document that never existed is the already-handled case."""
    store = _fake_store(monkeypatch)
    del store.documents[CONVERSATION_PATH]

    assert conversations_db.update_conversation(UID, CONVERSATION_ID, {'language': 'fr'}) is False


def test_update_live_document_still_writes_and_returns_true(monkeypatch):
    """Control: no race — the write lands exactly as before the fix."""
    store = _fake_store(monkeypatch, data_protection_level='standard', language='en')

    result = conversations_db.update_conversation(UID, CONVERSATION_ID, {'language': 'fr'})

    assert result is True
    assert store.documents[CONVERSATION_PATH]['language'] == 'fr'
    assert store.documents[CONVERSATION_PATH]['data_protection_level'] == 'standard'


def test_update_uses_the_snapshot_data_protection_level(monkeypatch):
    """The snapshot's data_protection_level still reaches the write prep.

    ``_prepare_conversation_for_write`` is driven for real; the enhanced level
    from the snapshot must not block the write path.
    """
    _fake_store(monkeypatch, data_protection_level='enhanced')

    assert conversations_db.update_conversation(UID, CONVERSATION_ID, {'language': 'fr'}) is True


def test_update_raced_by_delete_does_not_write_partial_data(monkeypatch):
    """Nothing from update_data may land when the owner is gone."""
    store = _fake_store(monkeypatch, data_protection_level='standard', language='en')
    store.delete_on_get.add(CONVERSATION_PATH)

    conversations_db.update_conversation(UID, CONVERSATION_ID, {'language': 'fr'})

    assert store.documents == {}


def test_update_race_returns_false_for_every_caller_write_shape(monkeypatch):
    """The contract holds for the plain field writes each caller makes —
    the pusher flush (audio_files), the events/action_items wrappers
    (structured.*), the calendar link (calendar_event), the deferral flag."""
    for payload in (
        {'audio_files': [{'path': 'audio.wav'}]},
        {'structured.events': []},
        {'structured.action_items': []},
        {'calendar_event': None},
        {'deferred': True},
    ):
        store = _fake_store(monkeypatch, data_protection_level='standard')
        store.delete_on_get.add(CONVERSATION_PATH)
        assert conversations_db.update_conversation(UID, CONVERSATION_ID, dict(payload)) is False


def test_lifecycle_fields_are_still_rejected(monkeypatch):
    """The lifecycle-owner guard precedes everything, race or not."""
    _fake_store(monkeypatch, data_protection_level='standard')
    with pytest.raises(ValueError, match='lifecycle fields'):
        conversations_db.update_conversation(UID, CONVERSATION_ID, {'status': 'processing'})


def test_lifecycle_fields_rejected_even_when_raced_by_delete(monkeypatch):
    """Guard ordering is load-bearing: it must not depend on Firestore state."""
    store = _fake_store(monkeypatch, data_protection_level='standard')
    store.delete_on_get.add(CONVERSATION_PATH)
    with pytest.raises(ValueError, match='lifecycle fields'):
        conversations_db.update_conversation(UID, CONVERSATION_ID, {'discarded': True})


def test_update_conversation_events_inherits_the_race_contract(monkeypatch):
    """The events wrapper routes through update_conversation, so the raced
    owner is a no-op instead of a NotFound escaping into its caller."""
    store = _fake_store(monkeypatch, data_protection_level='standard', structured={'events': []})
    store.delete_on_get.add(CONVERSATION_PATH)

    conversations_db.update_conversation_events(UID, CONVERSATION_ID, [{'type': 'app'}])

    assert store.documents == {}


def test_update_conversation_action_items_inherits_the_race_contract(monkeypatch):
    """The action_items wrapper inherits the same contract."""
    store = _fake_store(monkeypatch, data_protection_level='standard')
    store.delete_on_get.add(CONVERSATION_PATH)

    conversations_db.update_conversation_action_items(UID, CONVERSATION_ID, [{'title': 't'}])

    assert store.documents == {}


# ---------------------------------------------------------------------------
# Caller 1: the pusher's private-cloud flush (the signature's birthplace).
# ---------------------------------------------------------------------------

SAMPLE_RATE = 8000
CONVERSATION_FRAME = struct.pack('<I', 103) + CONVERSATION_ID.encode()
AUDIO_FRAME = struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\x00' * 64


class _AudioFile:
    def model_dump(self) -> dict:
        return {'path': 'audio.wav'}


class SequencedWebSocket:
    """Sends the second audio chunk only after the first flush was handled.

    Without this handshake the two chunks coalesce into one batch and the test
    cannot observe whether the pusher keeps uploading after the owner died.
    """

    def __init__(self, first_flush_handled: asyncio.Event):
        self.frames = deque([CONVERSATION_FRAME, AUDIO_FRAME])
        self.first_flush_handled = first_flush_handled
        self.second_chunk_sent = False
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        if self.frames:
            return self.frames.popleft()
        if not self.second_chunk_sent:
            await self.first_flush_handled.wait()
            self.second_chunk_sent = True
            return AUDIO_FRAME
        raise WebSocketDisconnect(1000)


@pytest.fixture
def raced_pusher_session(monkeypatch):
    """Drive the pusher's private-cloud worker where update_conversation hits
    the read-then-delete race (False) on the first flush."""
    import routers.pusher as pusher
    import utils.pusher_protocol as pusher_protocol

    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0.0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.01)

    first_flush_handled = asyncio.Event()
    uploaded: list[str] = []
    fallbacks: list[dict] = []

    def upload(chunks, uid, conversation_id, protection_level):
        uploaded.append(conversation_id)

    def run(update_result: bool):
        def update_conversation(uid, conversation_id, update_data):
            first_flush_handled.set()
            return update_result

        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
        monkeypatch.setattr(
            pusher.conversations_db, 'create_audio_files_from_chunks', lambda uid, conversation_id: [_AudioFile()]
        )
        monkeypatch.setattr(pusher.conversations_db, 'update_conversation', update_conversation)
        monkeypatch.setattr(pusher, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
        return SequencedWebSocket(first_flush_handled)

    return {'run': run, 'uploaded': uploaded, 'fallbacks': fallbacks}


@pytest.mark.asyncio
async def test_pusher_flush_raced_by_delete_takes_the_gone_owner_path(raced_pusher_session, caplog):
    """Before the fix, the race surfaced as the production ERROR signature.

    The pusher flush called update_conversation, the delete won, NotFound
    escaped to the broad except, and the session logged
    ``Error updating audio files: 404 No document to update`` — the designed
    gone-owner path (stop syncing, drop fallback) never ran. update_conversation
    returning False (the fix's contract) must drive that path silently.
    """
    import routers.pusher as pusher_mod

    websocket = raced_pusher_session['run'](update_result=False)

    with caplog.at_level(logging.ERROR, logger='routers.pusher'):
        await pusher_mod._websocket_util_trigger(websocket, UID, SAMPLE_RATE)

    # The first batch races the delete and is unavoidable; the second must not upload.
    assert raced_pusher_session['uploaded'] == [CONVERSATION_ID]
    assert raced_pusher_session['fallbacks'] == [
        {
            'component': 'pusher',
            'from_mode': 'private_cloud_sync',
            'to_mode': 'drop',
            'reason': 'policy',
            'outcome': 'exhausted',
            'log': pusher_mod.logger,
        }
    ]
    # The race must no longer surface as an ERROR log.
    assert not [r for r in caplog.records if 'Error updating audio files' in r.getMessage()]


@pytest.mark.asyncio
async def test_pusher_flush_still_errors_on_a_real_storage_failure(raced_pusher_session, caplog):
    """Guard against over-broad suppression: a genuine (non-race) failure in
    the flush must still be logged at ERROR, not silently dropped.

    The first flush completes normally (it arms the sequenced websocket); the
    second flush's chunk listing raises.
    """
    import routers.pusher as pusher_mod

    websocket = raced_pusher_session['run'](update_result=True)

    calls = {'n': 0}

    def flaky_create(uid, conversation_id):
        calls['n'] += 1
        if calls['n'] == 1:
            return [_AudioFile()]
        raise RuntimeError('storage exploded')

    mp = pytest.MonkeyPatch()
    mp.setattr(pusher_mod.conversations_db, 'create_audio_files_from_chunks', flaky_create)
    try:
        with caplog.at_level(logging.ERROR, logger='routers.pusher'):
            await pusher_mod._websocket_util_trigger(websocket, UID, SAMPLE_RATE)
        assert [
            r for r in caplog.records if 'Error updating audio files' in r.getMessage()
        ], 'a genuine flush failure must still be logged at ERROR'
    finally:
        mp.undo()


# ---------------------------------------------------------------------------
# Caller 2: the sync pipeline's offline finalizer.
# ---------------------------------------------------------------------------


def test_sync_finalizer_raced_by_delete_is_not_an_error(monkeypatch, caplog):
    """``_finalize_sync_audio_files`` must not log outcome=failed for the race.

    The finalizer persists audio_files per conversation with a broad except
    that logs ``event=sync_audio_finalize outcome=failed`` — before the fix the
    gone-owner race landed in that ERROR. After the fix the False return makes
    the persist a no-op (the conversation is gone, there is nothing to persist
    onto) and the ERROR signature disappears.
    """
    from utils.sync import pipeline as sync_pipeline

    def update_conversation(uid, conversation_id, update_data):
        return False  # the race outcome after the fix

    monkeypatch.setattr(
        sync_pipeline.conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: [_AudioFile()]
    )
    monkeypatch.setattr(sync_pipeline.conversations_db, 'update_conversation', update_conversation)
    monkeypatch.setattr(sync_pipeline, 'precache_conversation_audio', lambda *a, **k: None)
    monkeypatch.setattr(sync_pipeline, 'is_audio_merge_dispatch_enabled', lambda: False)

    response = {'new_memories': {CONVERSATION_ID}, 'updated_memories': set()}
    with caplog.at_level(logging.ERROR, logger='utils.sync.pipeline'):
        sync_pipeline._finalize_sync_audio_files(UID, response)

    assert not [r for r in caplog.records if 'sync_audio_finalize' in r.getMessage()]


def test_sync_finalizer_still_errors_on_a_real_failure(monkeypatch, caplog):
    """Over-broad suppression guard: a genuine finalizer failure still logs."""
    from utils.sync import pipeline as sync_pipeline

    def boom(uid, cid):
        raise RuntimeError('storage exploded')

    monkeypatch.setattr(sync_pipeline.conversations_db, 'create_audio_files_from_chunks', boom)
    monkeypatch.setattr(sync_pipeline, 'precache_conversation_audio', lambda *a, **k: None)
    monkeypatch.setattr(sync_pipeline, 'is_audio_merge_dispatch_enabled', lambda: False)

    response = {'new_memories': {CONVERSATION_ID}, 'updated_memories': set()}
    with caplog.at_level(logging.ERROR, logger='utils.sync.pipeline'):
        sync_pipeline._finalize_sync_audio_files(UID, response)

    assert [r for r in caplog.records if 'sync_audio_finalize' in r.getMessage()]
