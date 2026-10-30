"""Portability export must carry verified plaintext, never ciphertext.

These tests seed documents through the production write/encrypt helpers and run
the real bulk readers against a fake Firestore authority, so a decrypt fallback
returning ciphertext or a wrong-owner key fails the export instead of shipping
a silently truncated or ciphertext-bearing archive.
"""

from __future__ import annotations

import base64
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from database import _client as database_client
from database import chat as chat_db
from database import conversations as conversations_db
from database import memories as memories_db
from services.users import data_export
from utils import encryption
from utils.memory import memory_service as memory_service_module
from utils.memory.memory_service import MemoryService
from utils.other.portability_read import PortabilityReadVerificationError

UID = 'uid1'
OTHER_UID = 'uid2'
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

SEGMENTS = [{'text': 'hello export world', 'speaker': 'SPEAKER_0', 'start': 0.0, 'end': 1.0}]
SPEAKER_MAP = {'SPEAKER_0': {'person_id': 'person1'}}
PNG_BYTES = b'\x89PNG\r\n\x1a\npng-bytes'
MEMORY_CONTENT = 'the user likes plain croissants'
MEMORY_EVIDENCE = [{'evidence_id': 'ev1', 'independence_group': 'g1', 'source_type': 'conversation'}]
CHAT_TEXT = 'chat message plaintext'


class _DocRef:
    def __init__(self, path: str, db: '_FakeDb' | None = None, doc_id: str = ''):
        self.path = path
        self._db = db
        self._doc_id = doc_id

    def collection(self, name: str) -> '_Query':
        return _Query(self._db.nested.get((self._doc_id, name), []) if self._db else [])


class _Doc:
    def __init__(self, payload: Dict[str, Any], doc_id: str, path: str, db: '_FakeDb'):
        self._payload = payload
        self.id = doc_id
        self.reference = _DocRef(path, db, doc_id)

    def to_dict(self):
        return self._payload


class _Query:
    """Minimal ordered query: where/order/limit/start_after are no-ops over the fixture docs."""

    def __init__(self, docs: List[_Doc]):
        self._docs = docs

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, _n):
        return self

    def start_after(self, _cursor):
        return self

    def stream(self):
        yield from self._docs


class _UserDocument:
    def __init__(self, db: '_FakeDb', uid: str):
        self._db = db
        self._uid = uid

    def collection(self, name: str) -> _Query:
        docs = [
            _Doc(payload, str(payload.get('id', f'{name}-{i}')), f'users/{self._uid}/{name}/{i}', self._db)
            for i, payload in enumerate(self._db.collections.get(name, []))
        ]
        return _Query(docs)


class _UsersCollection:
    def __init__(self, db: '_FakeDb'):
        self._db = db

    def document(self, uid: str) -> _UserDocument:
        return _UserDocument(self._db, uid)


class _FakeDb:
    """Firestore stand-in: owner subcollections, a photos collection group, and document refs."""

    def __init__(self):
        self.collections: Dict[str, List[Dict[str, Any]]] = {}
        self.photos: List[_Doc] = []
        self.nested: Dict[tuple, List[_Doc]] = {}

    def collection(self, name: str) -> _UsersCollection:
        assert name == 'users'
        return _UsersCollection(self)

    def collection_group(self, name: str) -> _Query:
        assert name == 'photos'
        return _Query(self.photos)

    def document(self, path: str) -> _DocRef:
        return _DocRef(path)


def _photo_doc(uid: str, conversation_id: str, photo_id: str, payload: Dict[str, Any]) -> _Doc:
    return _Doc(payload, photo_id, f'users/{uid}/conversations/{conversation_id}/photos/{photo_id}', None)


def _encrypted_conversation(uid: str = UID) -> Dict[str, Any]:
    return conversations_db.encode_conversation_for_write(
        uid,
        {
            'id': 'conv1',
            'created_at': NOW,
            'transcript_segments': SEGMENTS,
            'manual_speaker_assignments': SPEAKER_MAP,
            'data_protection_level': 'enhanced',
        },
        'enhanced',
    )


def _encrypted_photo(uid: str = UID) -> Dict[str, Any]:
    return conversations_db.prepare_photo_for_write(
        {
            'id': 'photo1',
            'base64': base64.b64encode(PNG_BYTES).decode('ascii'),
            'content_type': 'image/png',
            'created_at': NOW,
        },
        uid,
        'enhanced',
    )


def _encrypted_message(uid: str = UID) -> Dict[str, Any]:
    return chat_db._encrypt_chat_data(
        {
            'id': 'msg1',
            'text': CHAT_TEXT,
            'created_at': NOW,
            'data_protection_level': 'enhanced',
        },
        uid,
    )


def _encrypted_memory(uid: str = UID) -> Dict[str, Any]:
    return memories_db._encrypt_memory_data(
        {
            'id': 'mem1',
            'content': MEMORY_CONTENT,
            'evidence': list(MEMORY_EVIDENCE),
            'category': 'interesting',
            'visibility': 'private',
            'created_at': NOW,
            'updated_at': NOW,
            'data_protection_level': 'enhanced',
        },
        uid,
    )


def _install_memory_history(monkeypatch, raw_memories: List[Dict[str, Any]]):
    """Feed the real MemoryService history scan through faked Firestore pages only."""
    service = MemoryService()
    cursors = [(NOW, str(raw.get('id'))) for raw in raw_memories]
    monkeypatch.setattr(memory_service_module, 'iter_authoritative_product_memory_items', lambda **_kwargs: iter([]))
    monkeypatch.setattr(
        memories_db,
        'scan_memories_updated_at_page',
        lambda _uid, **_kwargs: (list(raw_memories), cursors, True),
    )
    monkeypatch.setattr(memories_db, 'scan_memories_created_at_page', lambda _uid, **_kwargs: ([], [], True))
    service.canonical_statuses = MagicMock(return_value={})
    monkeypatch.setattr(data_export, 'MemoryService', MagicMock(return_value=service))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(database_client, 'db', db)
    monkeypatch.setattr(database_client, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations_db, 'db', db)
    monkeypatch.setattr(chat_db, 'db', db)
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={'name': 'u'}))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'iter_all_action_items', MagicMock(return_value=iter([])))
    _install_memory_history(monkeypatch, [])
    return db


def _export_body(streaming: bool) -> str:
    if streaming:
        return ''.join(data_export.iter_user_data_export_streaming(UID))
    return ''.join(data_export.iter_user_data_export(UID))


def _populate_encrypted_sections(db: _FakeDb) -> None:
    db.collections['conversations'] = [_encrypted_conversation()]
    db.photos = [_photo_doc(UID, 'conv1', 'photo1', _encrypted_photo())]
    db.collections['messages'] = [_encrypted_message()]
    db.collections['frame_requests'] = [
        {
            'id': 'fr1',
            'state': 'completed',
            'cleanup_state': 'deleted',
            'storage_id': 'obj-1',
            'created_at': NOW,
        }
    ]


@pytest.mark.parametrize('streaming', [True, False], ids=['streaming', 'legacy'])
def test_export_decrypts_all_encrypted_field_families(fake_db, monkeypatch, streaming):
    _populate_encrypted_sections(fake_db)
    _install_memory_history(monkeypatch, [_encrypted_memory()])

    payload = json.loads(_export_body(streaming))

    conversation = payload['conversations'][0]
    assert conversation['transcript_segments'] == SEGMENTS
    assert conversation['manual_speaker_assignments'] == SPEAKER_MAP

    manifest = payload['conversation_photo_manifest'][0]
    assert base64.b64decode(manifest['bytes_base64']) == PNG_BYTES

    memory = payload['memories'][0]
    assert memory['content'] == MEMORY_CONTENT
    evidence = memory['evidence'][0]
    for key, value in MEMORY_EVIDENCE[0].items():
        assert evidence[key] == value

    assert payload['chat_messages'][0]['text'] == CHAT_TEXT
    assert payload['frame_requests'][0]['id'] == 'fr1'
    if streaming:
        assert payload['export_complete'] is True


def test_late_sections_follow_chat_messages_in_both_variants(fake_db, monkeypatch):
    _populate_encrypted_sections(fake_db)

    streaming_body = _export_body(True)
    streaming_payload = json.loads(streaming_body)
    assert streaming_body.endswith(',\n  "export_complete": true\n}\n')
    assert list(streaming_payload)[-4:] == [
        'chat_messages',
        'conversation_photo_manifest',
        'frame_requests',
        'export_complete',
    ]

    legacy_payload = json.loads(_export_body(False))
    assert 'export_complete' not in legacy_payload
    assert list(legacy_payload)[-3:] == ['chat_messages', 'conversation_photo_manifest', 'frame_requests']


def _corrupt(payload: Dict[str, Any], field: str) -> Dict[str, Any]:
    corrupted = dict(payload)
    value = corrupted[field]
    corrupted[field] = value[:-4] + ('AAAA' if not value.endswith('AAAA') else 'BBBB')
    return corrupted


def _seed_tampered_family(fake_db: _FakeDb, monkeypatch, family: str, tamper: str) -> None:
    owner = OTHER_UID if tamper == 'wrong_owner' else UID
    corrupt = tamper == 'corrupt'
    if family == 'transcript':
        doc = _encrypted_conversation()
        if corrupt:
            doc = _corrupt(doc, 'transcript_segments')
        elif tamper == 'wrong_owner':
            doc['transcript_segments'] = _encrypted_conversation(uid=OTHER_UID)['transcript_segments']
        fake_db.collections['conversations'] = [doc]
    elif family == 'manual_speakers':
        doc = _encrypted_conversation()
        if corrupt:
            doc = _corrupt(doc, 'manual_speaker_assignments')
        elif tamper == 'wrong_owner':
            doc['manual_speaker_assignments'] = _encrypted_conversation(uid=OTHER_UID)['manual_speaker_assignments']
        fake_db.collections['conversations'] = [doc]
    elif family == 'photo':
        doc = _encrypted_photo(uid=owner)
        fake_db.photos = [_photo_doc(UID, 'conv1', 'photo1', _corrupt(doc, 'base64') if corrupt else doc)]
    elif family == 'chat':
        doc = _encrypted_message(uid=owner)
        fake_db.collections['messages'] = [_corrupt(doc, 'text') if corrupt else doc]
    elif family == 'memory_content':
        doc = _encrypted_memory()
        if corrupt:
            doc = _corrupt(doc, 'content')
        elif tamper == 'wrong_owner':
            doc['content'] = _encrypted_memory(uid=OTHER_UID)['content']
        _install_memory_history(monkeypatch, [doc])
    elif family == 'memory_evidence':
        doc = _encrypted_memory()
        if corrupt:
            doc = _corrupt(doc, 'evidence')
        elif tamper == 'wrong_owner':
            doc['evidence'] = _encrypted_memory(uid=OTHER_UID)['evidence']
        _install_memory_history(monkeypatch, [doc])
    else:
        raise AssertionError(f'unknown family {family}')


@pytest.mark.parametrize('streaming', [True, False], ids=['streaming', 'legacy'])
@pytest.mark.parametrize('tamper', ['wrong_owner', 'corrupt'])
@pytest.mark.parametrize(
    'family',
    ['transcript', 'manual_speakers', 'photo', 'chat', 'memory_content', 'memory_evidence'],
)
def test_tampered_encrypted_family_fails_export(fake_db, monkeypatch, family, tamper, streaming):
    _seed_tampered_family(fake_db, monkeypatch, family, tamper)

    expected_error = ValueError if family == 'transcript' else PortabilityReadVerificationError
    parts = []
    with pytest.raises(expected_error):
        if streaming:
            for chunk in data_export.iter_user_data_export_streaming(UID):
                parts.append(chunk)
        else:
            data_export.iter_user_data_export(UID)
    assert not ''.join(parts).endswith(',\n  "export_complete": true\n}\n')


@pytest.mark.parametrize('streaming', [True, False], ids=['streaming', 'legacy'])
def test_malformed_decrypted_memory_evidence_fails_under_export(fake_db, monkeypatch, streaming):
    raw = _encrypted_memory()
    raw['evidence'] = encryption.encrypt('not-json-evidence', UID)
    _install_memory_history(monkeypatch, [raw])

    with pytest.raises(json.JSONDecodeError):
        if streaming:
            for _ in data_export.iter_user_data_export_streaming(UID):
                pass
        else:
            data_export.iter_user_data_export(UID)

    prepared = memories_db.prepare_memory_for_read(raw, UID)
    assert prepared['evidence'] == raw['evidence']


def test_display_fallback_reads_still_tolerate_bad_ciphertext_outside_export(fake_db):
    photo = _corrupt(_encrypted_photo(), 'base64')
    prepared = conversations_db.prepare_photo_for_read(photo, UID)
    assert prepared['base64'] == photo['base64']

    message = _corrupt(_encrypted_message(), 'text')
    prepared_message = chat_db.decrypt_message_payload(message, UID)
    assert prepared_message['text'] == message['text']


def test_late_image_read_does_not_block_text_sections(fake_db, monkeypatch):
    _populate_encrypted_sections(fake_db)
    entered = threading.Event()
    release = threading.Event()

    def _gated_photos(uid):
        assert release.wait(timeout=10), 'photo gate never released'
        entered.set()
        yield 'conv1', conversations_db.prepare_photo_for_read(_encrypted_photo(), uid)

    monkeypatch.setattr(
        data_export.conversations_db, 'iter_all_conversation_photos', MagicMock(side_effect=_gated_photos)
    )

    parts = []
    done = threading.Event()
    error: List[BaseException] = []

    def _consume():
        try:
            for chunk in data_export.iter_user_data_export_streaming(UID):
                parts.append(chunk)
        except BaseException as exc:
            error.append(exc)
        finally:
            done.set()

    worker = threading.Thread(target=_consume)
    worker.start()
    try:
        for _ in range(1000):
            body = ''.join(parts)
            if '"chat_messages"' in body:
                break
            if done.wait(timeout=0.01):
                break
        body = ''.join(parts)
        assert '"chat_messages"' in body
        assert '"memories"' in body
        assert '"task_data"' in body
        assert 'conversation_photo_manifest' not in body
        assert 'image_manifest' not in body
        assert not entered.is_set()
    finally:
        release.set()
    done.wait(timeout=10)
    worker.join(timeout=10)
    assert not error
    body = ''.join(parts)
    assert 'conversation_photo_manifest' in body
    assert body.endswith(',\n  "export_complete": true\n}\n')


def test_failing_image_section_yields_no_completion(fake_db, monkeypatch):
    _populate_encrypted_sections(fake_db)

    def _failing_photos(uid):
        yield 'conv1', conversations_db.prepare_photo_for_read(_encrypted_photo(), uid)
        raise RuntimeError('photo stream failed')

    monkeypatch.setattr(
        data_export.conversations_db, 'iter_all_conversation_photos', MagicMock(side_effect=_failing_photos)
    )

    parts = []
    with pytest.raises(RuntimeError, match='photo stream failed'):
        for chunk in data_export.iter_user_data_export_streaming(UID):
            parts.append(chunk)

    body = ''.join(parts)
    assert '"chat_messages"' in body
    assert not body.endswith(',\n  "export_complete": true\n}\n')
