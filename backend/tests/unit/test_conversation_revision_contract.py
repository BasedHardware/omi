import json
import zlib
from datetime import datetime, timezone

import pytest

import database.conversations as conversations_db
from database.store.adapters.firestore import _revision as _firestore_revision
from models.conversation import Conversation, ConversationMutationResponse
from models.structured import Structured
from tests.store_fakes import FakeDocumentStore


class _TimestampLike:
    """A protobuf ``Timestamp``-shaped value (seconds/nanos, no ``ToDatetime``)."""

    def __init__(self, seconds, nanos):
        self.seconds = seconds
        self.nanos = nanos


class _SnapshotLike:
    """A Firestore snapshot exposing only ``update_time`` (what the adapter reads)."""

    def __init__(self, update_time):
        self.update_time = update_time


class _Record:
    """A neutral ``StoredDocument``-shaped stand-in: ``to_dict()`` + ``updated_at`` (ADR-0017)."""

    def __init__(self, data, updated_at=None):
        self._data = data
        self.updated_at = updated_at

    def to_dict(self):
        return None if self._data is None else dict(self._data)


def _conv_path(conversation_id: str, uid: str = 'user-1') -> str:
    return conversations_db._conversation_path(uid, conversation_id)


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(conversations_db, '_store', lambda: fake)
    return fake


# --- Neutral revision (ADR-0017): the adapter normalizes SDK variation, the domain passes it through.


def test_document_data_with_revision_stamps_the_neutral_updated_at():
    revision = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    result = conversations_db._document_data_with_revision(_Record({'id': 'conversation-1'}, updated_at=revision))

    assert result == {'id': 'conversation-1', 'updated_at': revision}


def test_document_data_with_revision_of_missing_document_is_none():
    assert conversations_db._document_data_with_revision(_Record(None)) is None


def test_adapter_normalizes_protobuf_like_update_time():
    # The revision normalization moved to the adapter boundary (ADR-0017); the production client
    # returns a DatetimeWithNanoseconds, while emulators/fakes may expose protobuf seconds/nanos.
    revision = _firestore_revision(_SnapshotLike(_TimestampLike('1783598400', '125000')))

    assert revision == datetime(2026, 7, 9, 12, 0, 0, 125000, tzinfo=timezone.utc)


def test_adapter_normalizes_protobuf_nanoseconds_with_the_official_integer_scale():
    revision = _firestore_revision(_SnapshotLike(_TimestampLike(1783598400, 125_000_000)))

    assert revision == datetime(2026, 7, 9, 12, 0, 0, 125000, tzinfo=timezone.utc)


def test_adapter_makes_a_naive_datetime_utc_aware():
    revision = _firestore_revision(_SnapshotLike(datetime(2026, 7, 9, 12, 0)))

    assert revision == datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


# --- Read projection.


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


# --- Processing upsert lifecycle (transaction-backed).


def test_processing_upsert_preserves_every_user_owned_field(store):
    store.set(
        _conv_path('conversation-1'),
        {
            'id': 'conversation-1',
            'structured': {'title': 'My title', 'overview': 'Old summary'},
            'user_title': 'My title',
            'starred': True,
            'folder_id': 'important',
            'visibility': 'shared',
            'data_protection_level': 'standard',
        },
    )

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated replacement', 'overview': 'Fresh summary'},
            'starred': False,
            'folder_id': None,
            'visibility': 'private',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['structured'] == {'title': 'My title', 'overview': 'Fresh summary'}
    assert written['user_title'] == 'My title'
    assert written['starred'] is True
    assert written['folder_id'] == 'important'
    assert written['visibility'] == 'shared'
    assert written['status'] == 'completed'


def test_processing_upsert_fills_user_fields_the_stub_left_null(store):
    """Regression: the in-progress stub written at transcribe time dumps
    folder_id/user_title as None. A null existing value means "never user-set"
    and must not revert the AI folder assignment made during processing."""
    store.set(
        _conv_path('conversation-1'),
        {
            'id': 'conversation-1',
            'structured': {'title': 'In progress'},
            'starred': False,
            'folder_id': None,
            'visibility': 'private',
            'user_title': None,
            'data_protection_level': 'standard',
        },
    )

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated title'},
            'folder_id': 'ai-assigned-folder',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['folder_id'] == 'ai-assigned-folder'
    # Non-null user-owned values are still preserved.
    assert written['starred'] is False
    assert written['visibility'] == 'private'
    assert written['structured']['title'] == 'Generated title'


def test_first_processing_write_still_creates_complete_document(store):
    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'updated_at': datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
            'structured': {'title': 'Generated title'},
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    # updated_at is server metadata, never replayed into the stored document.
    assert 'updated_at' not in written
    assert written['structured']['title'] == 'Generated title'


def test_create_if_absent_never_persists_firestore_revision_metadata(store):
    conversations_db.create_conversation_if_absent_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'updated_at': datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
            'structured': {'title': 'Generated title'},
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert 'updated_at' not in written


def test_processing_transaction_reloads_user_fields_when_the_store_retries(monkeypatch):
    # Regression: the read-modify-write must re-read on a contention retry so a concurrent user
    # edit that lands mid-transaction is preserved, not clobbered by the stale in-memory result.
    path = _conv_path('conversation-1')

    class _RetryOnceStore(FakeDocumentStore):
        def run_transaction(self, fn, *, attempts=3):
            super().run_transaction(fn)  # first attempt lands
            # a concurrent user edit lands between attempts (renamed + starred + foldered)
            self.set(
                path,
                {
                    'id': 'conversation-1',
                    'structured': {'title': 'User renamed'},
                    'user_title': 'User renamed',
                    'starred': True,
                    'folder_id': 'user-folder',
                    'data_protection_level': 'standard',
                },
            )
            return super().run_transaction(fn)  # retry re-reads the new state

    store = _RetryOnceStore()
    store.set(
        path,
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated'},
            'starred': False,
            'data_protection_level': 'standard',
        },
    )
    monkeypatch.setattr(conversations_db, '_store', lambda: store)

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated replacement', 'overview': 'Fresh summary'},
            'starred': False,
            'folder_id': None,
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(path).to_dict()
    assert written['structured']['title'] == 'User renamed'
    assert written['structured']['overview'] == 'Fresh summary'
    assert written['starred'] is True
    assert written['folder_id'] == 'user-folder'


def test_title_mutation_records_a_durable_override(store):
    store.set(_conv_path('conversation-1'), {'id': 'conversation-1'})

    conversations_db.update_conversation_title('user-1', 'conversation-1', 'Renamed')

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['structured']['title'] == 'Renamed'
    assert written['user_title'] == 'Renamed'


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


# --- Segment text edit (transaction-backed read-modify-write).


def _seed_segments(store, segments, *, is_locked=False):
    store.set(
        _conv_path('conv-1'),
        {'data_protection_level': 'standard', 'is_locked': is_locked, 'transcript_segments': segments},
    )


def test_segment_text_edit_reads_and_writes_inside_a_transaction(store):
    # Regression for #9392: the read-modify-write must be atomic so concurrent
    # edits to different segments can't lose-update each other.
    _seed_segments(store, [{'id': 's1', 'text': 'old'}, {'id': 's2', 'text': 'keep'}])

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'new text')

    assert result == 'ok'
    stored = store.get(_conv_path('conv-1')).to_dict()['transcript_segments']
    written = json.loads(zlib.decompress(stored).decode('utf-8'))
    assert {s['id']: s['text'] for s in written} == {'s1': 'new text', 's2': 'keep'}


def test_segment_text_edit_missing_segment_does_not_write(store):
    _seed_segments(store, [{'id': 's1', 'text': 'old'}])

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 'missing', 'x')

    assert result == 'segment_not_found'
    # No write happened: the segments are still the untouched plain seed.
    assert store.get(_conv_path('conv-1')).to_dict()['transcript_segments'] == [{'id': 's1', 'text': 'old'}]


def test_segment_text_edit_rejects_locked_conversation(store):
    _seed_segments(store, [{'id': 's1', 'text': 'old'}], is_locked=True)

    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'x')

    assert result == 'locked'
    assert store.get(_conv_path('conv-1')).to_dict()['transcript_segments'] == [{'id': 's1', 'text': 'old'}]


def test_segment_text_edit_missing_conversation_returns_not_found(store):
    result = conversations_db.update_conversation_segment_text('user-1', 'conv-1', 's1', 'x')

    assert result == 'not_found'
    assert not store.exists(_conv_path('conv-1'))


def test_processing_upsert_preserves_explicit_user_unfile_on_completed_conversation(store):
    """Regression (PR review): a user can explicitly move a conversation to no
    folder (PATCH /v1/conversations/{id}/folder with folder_id null). That
    write stamps folder_user_set, so the explicit-null state is user-owned and
    must not be overwritten by an AI folder assignment replayed by upsert."""
    store.set(
        _conv_path('conversation-1'),
        {
            'id': 'conversation-1',
            'structured': {'title': 'My title'},
            'starred': False,
            'folder_id': None,
            'folder_user_set': True,
            'visibility': 'private',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated title'},
            'folder_id': 'ai-assigned-folder',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['folder_id'] is None


def test_processing_upsert_preserves_unfile_raced_against_in_flight_processing(store):
    """Regression (PR review): the user clears the folder while processing is
    still in flight — the stored doc is still the in-progress stub, but the
    folder_user_set marker makes the explicit null win over the AI assignment.
    A status-based guard would miss this case; the marker must not."""
    store.set(
        _conv_path('conversation-1'),
        {
            'id': 'conversation-1',
            'structured': {'title': 'In progress'},
            'folder_id': None,
            'folder_user_set': True,
            'visibility': 'private',
            'status': 'in_progress',
            'data_protection_level': 'standard',
        },
    )

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated title'},
            'folder_id': 'ai-assigned-folder',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['folder_id'] is None


def test_processing_upsert_still_fills_stub_null_when_user_never_touched_folder(store):
    """The original fix stays intact: without folder_user_set, a stub's null
    folder_id is "never user-set" and the AI assignment wins."""
    store.set(
        _conv_path('conversation-1'),
        {
            'id': 'conversation-1',
            'structured': {'title': 'In progress'},
            'folder_id': None,
            'visibility': 'private',
            'status': 'in_progress',
            'data_protection_level': 'standard',
        },
    )

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'structured': {'title': 'Generated title'},
            'folder_id': 'ai-assigned-folder',
            'status': 'completed',
            'data_protection_level': 'standard',
        },
    )

    written = store.get(_conv_path('conversation-1')).to_dict()
    assert written['folder_id'] == 'ai-assigned-folder'
