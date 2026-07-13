from datetime import datetime, timezone

import database.conversations as conversations_db
from models.conversation import Conversation, ConversationMutationResponse
from models.structured import Structured


class _Snapshot:
    def __init__(self, data, update_time=None, exists=True):
        self._data = data
        self.update_time = update_time
        self.exists = exists

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _TimestampLike:
    def __init__(self, seconds, nanos):
        self.seconds = seconds
        self.nanos = nanos


class _ConversationRef:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.set_calls = []
        self.update_calls = []
        self.create_calls = []

    def get(self, transaction=None):
        return self.snapshot

    def set(self, data, **kwargs):
        self.set_calls.append((data, kwargs))

    def update(self, data):
        self.update_calls.append(data)

    def create(self, data):
        self.create_calls.append(data)


class _DocumentPath:
    def __init__(self, ref):
        self.ref = ref

    def collection(self, _name):
        return self

    def document(self, document_id):
        return self if document_id == 'user-1' else self.ref


class _Firestore:
    def __init__(self, ref):
        self.path = _DocumentPath(ref)

    def collection(self, _name):
        return self.path

    def transaction(self):
        return _Transaction()


class _Transaction:
    def set(self, ref, data, **kwargs):
        ref.set(data, **kwargs)

    def update(self, ref, data):
        ref.update(data)


def test_document_update_time_is_exposed_as_server_revision():
    revision = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    result = conversations_db._document_data_with_revision(_Snapshot({'id': 'conversation-1'}, update_time=revision))

    assert result == {'id': 'conversation-1', 'updated_at': revision}


def test_protobuf_like_document_update_time_is_normalized_for_api_models():
    result = conversations_db._document_data_with_revision(
        _Snapshot({'id': 'conversation-1'}, update_time=_TimestampLike('1783598400', '125000'))
    )

    assert result == {
        'id': 'conversation-1',
        'updated_at': datetime(2026, 7, 9, 12, 0, 0, 125000, tzinfo=timezone.utc),
    }


def test_protobuf_nanoseconds_use_the_official_integer_scale():
    result = conversations_db._document_data_with_revision(
        _Snapshot({'id': 'conversation-1'}, update_time=_TimestampLike(1783598400, 125_000_000))
    )

    assert result['updated_at'] == datetime(2026, 7, 9, 12, 0, 0, 125000, tzinfo=timezone.utc)


def test_user_title_override_is_the_read_projection():
    result = conversations_db._prepare_conversation_for_read(
        {
            'structured': {'title': 'Generated title', 'overview': 'Fresh summary'},
            'user_title': 'My durable title',
            'data_protection_level': 'standard',
        },
        'user-1',
    )

    assert result['structured']['title'] == 'My durable title'
    assert result['structured']['overview'] == 'Fresh summary'


def test_processing_upsert_preserves_every_user_owned_field(monkeypatch):
    existing = {
        'id': 'conversation-1',
        'structured': {'title': 'My title', 'overview': 'Old summary'},
        'user_title': 'My title',
        'starred': True,
        'folder_id': 'important',
        'visibility': 'shared',
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated replacement', 'overview': 'Fresh summary'},
        'starred': False,
        'folder_id': None,
        'visibility': 'private',
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    assert len(ref.set_calls) == 1
    written, options = ref.set_calls[0]
    assert options == {'merge': True}
    assert written['structured'] == {'title': 'My title', 'overview': 'Fresh summary'}
    assert written['user_title'] == 'My title'
    assert written['starred'] is True
    assert written['folder_id'] == 'important'
    assert written['visibility'] == 'shared'
    assert written['status'] == 'completed'


def test_processing_upsert_fills_user_fields_the_stub_left_null(monkeypatch):
    """Regression: the in-progress stub written at transcribe time dumps
    folder_id/user_title as None. A null existing value means "never user-set"
    and must not revert the AI folder assignment made during processing."""
    existing = {
        'id': 'conversation-1',
        'structured': {'title': 'In progress'},
        'starred': False,
        'folder_id': None,
        'visibility': 'private',
        'user_title': None,
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title'},
        'folder_id': 'ai-assigned-folder',
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    written, options = ref.set_calls[0]
    assert options == {'merge': True}
    assert written['folder_id'] == 'ai-assigned-folder'
    # Non-null user-owned values are still preserved.
    assert written['starred'] is False
    assert written['visibility'] == 'private'
    assert written['structured']['title'] == 'Generated title'


def test_first_processing_write_still_creates_complete_document(monkeypatch):
    ref = _ConversationRef(_Snapshot(None, exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'updated_at': datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
        'structured': {'title': 'Generated title'},
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    written, options = ref.set_calls[0]
    assert options == {}
    assert 'updated_at' not in written
    assert written['structured']['title'] == 'Generated title'


def test_create_if_absent_never_persists_firestore_revision_metadata(monkeypatch):
    ref = _ConversationRef(_Snapshot(None, exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    revision = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    conversations_db.create_conversation_if_absent(
        'user-1',
        {
            'id': 'conversation-1',
            'updated_at': revision,
            'structured': {'title': 'Generated title'},
            'data_protection_level': 'standard',
        },
    )

    assert len(ref.create_calls) == 1
    assert 'updated_at' not in ref.create_calls[0]


def test_processing_transaction_reloads_user_fields_when_firestore_retries(monkeypatch):
    ref = _ConversationRef(
        _Snapshot(
            {
                'id': 'conversation-1',
                'structured': {'title': 'Generated'},
                'starred': False,
                'data_protection_level': 'standard',
            }
        )
    )
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))

    def retry_once(function):
        def wrapper(transaction):
            function(transaction)
            ref.snapshot = _Snapshot(
                {
                    'id': 'conversation-1',
                    'structured': {'title': 'User renamed'},
                    'user_title': 'User renamed',
                    'starred': True,
                    'folder_id': 'user-folder',
                    'data_protection_level': 'standard',
                }
            )
            function(transaction)

        return wrapper

    monkeypatch.setattr(conversations_db.firestore, 'transactional', retry_once)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated replacement', 'overview': 'Fresh summary'},
        'starred': False,
        'folder_id': None,
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    retried_write, options = ref.set_calls[-1]
    assert options == {'merge': True}
    assert retried_write['structured']['title'] == 'User renamed'
    assert retried_write['structured']['overview'] == 'Fresh summary'
    assert retried_write['starred'] is True
    assert retried_write['folder_id'] == 'user-folder'


def test_title_mutation_records_a_durable_override(monkeypatch):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1'}))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))

    conversations_db.update_conversation_title('user-1', 'conversation-1', 'Renamed')

    assert ref.update_calls == [{'structured.title': 'Renamed', 'user_title': 'Renamed'}]


def test_mutation_response_contract_carries_canonical_revision_and_state():
    revision = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    canonical = Conversation(
        id='conversation-1',
        created_at=revision,
        updated_at=revision,
        started_at=revision,
        finished_at=revision,
        structured=Structured(title='Renamed', overview='Processing finished'),
        starred=True,
    )

    result = ConversationMutationResponse(status='Ok', conversation=canonical)

    assert result.conversation.updated_at == revision
    assert result.conversation.structured.title == 'Renamed'
    assert result.conversation.structured.overview == 'Processing finished'
    assert result.conversation.starred is True


def _segment_snapshot(segments, *, is_locked=False, exists=True):
    return _Snapshot(
        {
            'data_protection_level': 'standard',
            'is_locked': is_locked,
            'transcript_segments': segments,
        },
        exists=exists,
    )


def test_segment_text_edit_reads_and_writes_inside_a_transaction(monkeypatch):
    # Regression for #9392: the read-modify-write must be atomic so concurrent
    # edits to different segments can't lose-update each other.
    ref = _ConversationRef(_segment_snapshot([{'id': 's1', 'text': 'old'}, {'id': 's2', 'text': 'keep'}]))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'new text')

    assert result == 'ok'
    # The write went through the transaction (recorded on the ref), and the edit
    # landed while the untouched segment is preserved.
    assert len(ref.update_calls) == 1
    import json as _json
    import zlib as _zlib

    written = _json.loads(_zlib.decompress(ref.update_calls[0]['transcript_segments']).decode('utf-8'))
    assert {s['id']: s['text'] for s in written} == {'s1': 'new text', 's2': 'keep'}


def test_segment_text_edit_missing_segment_does_not_write(monkeypatch):
    ref = _ConversationRef(_segment_snapshot([{'id': 's1', 'text': 'old'}]))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 'missing', 'x')

    assert result == 'segment_not_found'
    assert ref.update_calls == []


def test_segment_text_edit_rejects_locked_conversation(monkeypatch):
    ref = _ConversationRef(_segment_snapshot([{'id': 's1', 'text': 'old'}], is_locked=True))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'x')

    assert result == 'locked'
    assert ref.update_calls == []


def test_segment_text_edit_missing_conversation_returns_not_found(monkeypatch):
    ref = _ConversationRef(_segment_snapshot([], exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'x')

    assert result == 'not_found'
    assert ref.update_calls == []


def test_processing_upsert_preserves_explicit_user_unfile_on_completed_conversation(monkeypatch):
    """Regression (PR review): a user can explicitly move a conversation to no
    folder (PATCH /v1/conversations/{id}/folder with folder_id null). That
    write stamps folder_user_set, so the explicit-null state is user-owned and
    must not be overwritten by an AI folder assignment replayed by upsert."""
    existing = {
        'id': 'conversation-1',
        'structured': {'title': 'My title'},
        'starred': False,
        'folder_id': None,
        'folder_user_set': True,
        'visibility': 'private',
        'status': 'completed',
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title'},
        'folder_id': 'ai-assigned-folder',
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    written, options = ref.set_calls[0]
    assert options == {'merge': True}
    assert written['folder_id'] is None


def test_processing_upsert_preserves_unfile_raced_against_in_flight_processing(monkeypatch):
    """Regression (PR review): the user clears the folder while processing is
    still in flight — the stored doc is still the in-progress stub, but the
    folder_user_set marker makes the explicit null win over the AI assignment.
    A status-based guard would miss this case; the marker must not."""
    existing = {
        'id': 'conversation-1',
        'structured': {'title': 'In progress'},
        'folder_id': None,
        'folder_user_set': True,
        'visibility': 'private',
        'status': 'in_progress',
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title'},
        'folder_id': 'ai-assigned-folder',
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    written, options = ref.set_calls[0]
    assert options == {'merge': True}
    assert written['folder_id'] is None


def test_processing_upsert_still_fills_stub_null_when_user_never_touched_folder(monkeypatch):
    """The original fix stays intact: without folder_user_set, a stub's null
    folder_id is "never user-set" and the AI assignment wins."""
    existing = {
        'id': 'conversation-1',
        'structured': {'title': 'In progress'},
        'folder_id': None,
        'visibility': 'private',
        'status': 'in_progress',
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    incoming = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title'},
        'folder_id': 'ai-assigned-folder',
        'status': 'completed',
        'data_protection_level': 'standard',
    }

    conversations_db.upsert_conversation('user-1', incoming)

    written, _ = ref.set_calls[0]
    assert written['folder_id'] == 'ai-assigned-folder'
