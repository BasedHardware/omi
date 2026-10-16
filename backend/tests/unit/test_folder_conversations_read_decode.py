"""Regression tests for folder conversation read decoding, visibility pagination, and count accuracy."""

from datetime import datetime, timezone
import json
from unittest.mock import patch
import zlib

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.conversations as conversations_db
import database.folders as folders_db
from models.conversation import Conversation
from utils import encryption
from utils.conversations.render import redact_conversations_for_list


class _Snapshot:
    def __init__(self, doc_id: str, data: dict | None, update_time: datetime | None = None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.update_time = update_time

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Aggregate:
    def __init__(self, total: int):
        self._total = total

    def get(self):
        return [[type('AggregationResult', (), {'value': self._total})()]]


class _Query:
    def __init__(
        self,
        rows: list[tuple[str, dict, datetime | None]],
        predicates: list[tuple[str, str, object]] | None = None,
        offset_val: int = 0,
        limit_val: int | None = None,
        after_id: str | None = None,
    ):
        self._rows = rows
        self._predicates = predicates or []
        self._offset = offset_val
        self._limit = limit_val
        self._after_id = after_id

    def where(self, filter=None):
        op = getattr(filter, 'op_string', '==')
        return _Query(
            self._rows,
            self._predicates + [(filter.field_path, op, filter.value)],
            offset_val=self._offset,
            limit_val=self._limit,
            after_id=self._after_id,
        )

    def order_by(self, _field: str, direction=None):
        return self

    def offset(self, n: int):
        return _Query(
            self._rows,
            list(self._predicates),
            offset_val=n,
            limit_val=self._limit,
            after_id=self._after_id,
        )

    def limit(self, n: int):
        return _Query(
            self._rows,
            list(self._predicates),
            offset_val=self._offset,
            limit_val=n,
            after_id=self._after_id,
        )

    def start_after(self, snapshot: _Snapshot):
        return _Query(
            self._rows,
            list(self._predicates),
            offset_val=0,
            limit_val=self._limit,
            after_id=snapshot.id,
        )

    def _matches(self, data: dict) -> bool:
        for field, op, value in self._predicates:
            actual = data.get(field)
            if op == '==':
                if actual != value:
                    return False
            elif op == '>':
                if not isinstance(actual, str) or not (actual > str(value)):
                    return False
            else:
                return False
        return True

    def _filtered_rows(self) -> list[tuple[str, dict, datetime | None]]:
        matched = [row for row in self._rows if self._matches(row[1])]
        if self._after_id is not None:
            for idx, (doc_id, _, _) in enumerate(matched):
                if doc_id == self._after_id:
                    matched = matched[idx + 1 :]
                    break
            else:
                matched = []
        if self._offset:
            matched = matched[self._offset :]
        if self._limit is not None:
            matched = matched[: self._limit]
        return matched

    def stream(self):
        for doc_id, data, update_time in self._filtered_rows():
            yield _Snapshot(doc_id, data, update_time=update_time)

    def count(self):
        return _Aggregate(len(self._filtered_rows()))


class _FolderDocRef:
    def __init__(self, folders_store: dict, folder_id: str):
        self._folders_store = folders_store
        self.id = folder_id

    def update(self, values: dict):
        self._folders_store.setdefault(self.id, {}).update(values)


class _FoldersCollection:
    def __init__(self, folders_store: dict):
        self._folders_store = folders_store

    def document(self, folder_id: str):
        return _FolderDocRef(self._folders_store, folder_id)


class _UserRef:
    def __init__(self, rows: list[tuple[str, dict, datetime | None]], folders_store: dict):
        self._rows = rows
        self._folders_store = folders_store

    def collection(self, name: str):
        if name == 'conversations':
            return _Query(self._rows)
        if name == 'folders':
            return _FoldersCollection(self._folders_store)
        raise AssertionError(f'Unexpected collection: {name}')


class _Db:
    def __init__(
        self,
        rows: list[tuple[str, dict, datetime | None]],
        folders_store: dict | None = None,
    ):
        self._rows = rows
        self.folders_store = folders_store if folders_store is not None else {}

    def collection(self, name: str):
        assert name == 'users'
        return type('Users', (), {'document': lambda _self, _uid: _UserRef(self._rows, self.folders_store)})()


def _compress_segments(segments: list[dict]) -> bytes:
    return zlib.compress(json.dumps(segments).encode('utf-8'))


def _encrypt_compressed_segments(segments: list[dict], uid: str) -> str:
    compressed = _compress_segments(segments)
    return encryption.encrypt(compressed.hex(), uid)


def test_get_conversations_in_folder_decodes_standard_compressed_and_validates_model():
    uid = 'u-folder-std'
    now = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    rev = datetime(2026, 10, 16, 8, 5, tzinfo=timezone.utc)
    raw_segments = [
        {
            'id': 'seg-1',
            'text': 'Hello folder world',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
            'start': 0.0,
            'end': 2.5,
        }
    ]
    rows = [
        (
            'conv-std-1',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'deleted': False,
                'created_at': now,
                'started_at': now,
                'finished_at': now,
                'structured': {
                    'title': 'Generated Title',
                    'overview': 'Summary text',
                    'category': 'work',
                    'action_items': [],
                    'events': [],
                },
                'user_title': 'User Custom Title',
                'data_protection_level': 'standard',
                'transcript_segments_compressed': True,
                'transcript_segments': _compress_segments(raw_segments),
                'live_transcript_replay_receipt': {'seq': 1},
            },
            rev,
        )
    ]
    fake_db = _Db(rows)
    with patch.object(folders_db, 'db', fake_db), patch.object(
        conversations_db, 'get_firestore_client', return_value=fake_db
    ):
        result = folders_db.get_conversations_in_folder(uid, 'f-work', limit=10, offset=0, include_discarded=False)

    assert len(result) == 1
    conv = result[0]
    assert conv['id'] == 'conv-std-1'
    assert isinstance(conv['transcript_segments'], list)
    assert conv['transcript_segments'][0]['text'] == 'Hello folder world'
    assert conv['structured']['title'] == 'User Custom Title'
    assert 'live_transcript_replay_receipt' not in conv
    assert conv['updated_at'] == rev

    redact_conversations_for_list(result)
    validated = Conversation.model_validate(conv)
    assert validated.id == 'conv-std-1'
    assert validated.structured.title == 'User Custom Title'
    assert len(validated.transcript_segments) == 1
    assert validated.transcript_segments[0].text == 'Hello folder world'


def test_get_conversations_in_folder_decrypts_enhanced_conversation():
    uid = 'u-folder-enh'
    now = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
    raw_segments = [
        {
            'id': 'seg-enh-1',
            'text': 'Confidential strategy notes',
            'speaker': 'SPEAKER_01',
            'speaker_id': 1,
            'is_user': True,
            'start': 1.0,
            'end': 4.0,
        }
    ]
    rows = [
        (
            'conv-enh-1',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'created_at': now,
                'started_at': now,
                'finished_at': now,
                'structured': {
                    'title': 'Strategy sync',
                    'overview': 'Overview',
                    'category': 'work',
                },
                'data_protection_level': 'enhanced',
                'transcript_segments_compressed': True,
                'transcript_segments': _encrypt_compressed_segments(raw_segments, uid),
            },
            now,
        )
    ]
    fake_db = _Db(rows)
    with patch.object(folders_db, 'db', fake_db), patch.object(
        conversations_db, 'get_firestore_client', return_value=fake_db
    ):
        result = folders_db.get_conversations_in_folder(uid, 'f-work', limit=10, offset=0, include_discarded=False)

    assert len(result) == 1
    assert isinstance(result[0]['transcript_segments'], list)
    assert result[0]['transcript_segments'][0]['text'] == 'Confidential strategy notes'
    validated = Conversation.model_validate(result[0])
    assert validated.id == 'conv-enh-1'
    assert validated.transcript_segments[0].text == 'Confidential strategy notes'


def test_get_conversations_in_folder_filters_hidden_rows_and_refills_page():
    uid = 'u-folder-page'
    now = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
    rows = [
        (
            'conv-deleted',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'deleted': True,
                'created_at': now,
                'structured': {'title': 'Deleted', 'overview': ''},
                'transcript_segments': [],
            },
            now,
        ),
        (
            'conv-dup',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'dream_duplicate_of': 'conv-primary',
                'created_at': now,
                'structured': {'title': 'Duplicate capture', 'overview': ''},
                'transcript_segments': [],
            },
            now,
        ),
        (
            'conv-visible-1',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'created_at': now,
                'structured': {'title': 'Visible 1', 'overview': 'Ok'},
                'transcript_segments': [],
            },
            now,
        ),
        (
            'conv-visible-2',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'created_at': now,
                'structured': {'title': 'Visible 2', 'overview': 'Ok'},
                'transcript_segments': [],
            },
            now,
        ),
    ]
    fake_db = _Db(rows)
    with patch.object(folders_db, 'db', fake_db), patch.object(
        conversations_db, 'get_firestore_client', return_value=fake_db
    ):
        result = folders_db.get_conversations_in_folder(uid, 'f-work', limit=2, offset=0, include_discarded=False)

    assert [c['id'] for c in result] == ['conv-visible-1', 'conv-visible-2']


def test_get_conversations_in_folder_include_discarded_skips_deleted_before_offset():
    uid = 'u-folder-discarded'
    now = datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc)
    rows = [
        (
            'conv-tombstone',
            {
                'folder_id': 'f-work',
                'discarded': True,
                'deleted': True,
                'created_at': now,
                'structured': {'title': 'Tombstone', 'overview': ''},
                'transcript_segments': [],
            },
            now,
        ),
        (
            'conv-discarded-visible',
            {
                'folder_id': 'f-work',
                'discarded': True,
                'deleted': False,
                'created_at': now,
                'structured': {'title': 'Discarded', 'overview': ''},
                'transcript_segments': [],
            },
            now,
        ),
        (
            'conv-active-visible',
            {
                'folder_id': 'f-work',
                'discarded': False,
                'deleted': False,
                'created_at': now,
                'structured': {'title': 'Active', 'overview': 'Ok'},
                'transcript_segments': [],
            },
            now,
        ),
    ]
    fake_db = _Db(rows)
    with patch.object(folders_db, 'db', fake_db), patch.object(
        conversations_db, 'get_firestore_client', return_value=fake_db
    ):
        first_page = folders_db.get_conversations_in_folder(uid, 'f-work', limit=1, offset=0, include_discarded=True)
        second_page = folders_db.get_conversations_in_folder(uid, 'f-work', limit=1, offset=1, include_discarded=True)

    assert [c['id'] for c in first_page] == ['conv-discarded-visible']
    assert [c['id'] for c in second_page] == ['conv-active-visible']


def test_update_folder_conversation_count_excludes_deleted_and_dream_duplicates():
    uid = 'u-folder-count'
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    rows = [
        ('c-visible', {'folder_id': 'f-work', 'discarded': False, 'deleted': False, 'created_at': now}, now),
        ('c-deleted', {'folder_id': 'f-work', 'discarded': False, 'deleted': True, 'created_at': now}, now),
        (
            'c-duplicate',
            {'folder_id': 'f-work', 'discarded': False, 'dream_duplicate_of': 'c-visible', 'created_at': now},
            now,
        ),
        ('c-other-folder', {'folder_id': 'f-personal', 'discarded': False, 'deleted': True, 'created_at': now}, now),
    ]
    fake_db = _Db(rows, folders_store={'f-work': {'conversation_count': 99}})
    with patch.object(folders_db, 'db', fake_db), patch.object(
        folders_db, 'get_firestore_client', return_value=fake_db
    ):
        updated_count = folders_db.update_folder_conversation_count(uid, 'f-work', firestore_client=fake_db)

    assert updated_count == 1
    assert fake_db.folders_store['f-work']['conversation_count'] == 1
