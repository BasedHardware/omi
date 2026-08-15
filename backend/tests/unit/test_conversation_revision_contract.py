from datetime import datetime, timezone

import database.conversations as conversations_db
import database.conversation_finalization_identity as finalization_identity_db
import database.conversation_write_fence as conversation_write_fence_db
import pytest
from google.api_core.exceptions import InvalidArgument
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
    def create(self, ref, data):
        ref.create(data)

    def set(self, ref, data, **kwargs):
        ref.set(data, **kwargs)

    def update(self, ref, data):
        ref.update(data)


@pytest.fixture(autouse=True)
def _transaction_contract_defaults(monkeypatch):
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(conversations_db, 'account_deletion_blocks_writes', lambda *args, **kwargs: False)
    monkeypatch.setattr(finalization_identity_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(finalization_identity_db, 'account_deletion_blocks_writes', lambda *args, **kwargs: False)
    monkeypatch.setattr(conversation_write_fence_db, 'account_deletion_blocks_writes', lambda *args, **kwargs: False)


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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

    written, options = ref.set_calls[0]
    assert options == {}
    assert 'updated_at' not in written
    assert written['structured']['title'] == 'Generated title'
    assert isinstance(written['finalization_incarnation_id'], str)
    assert written['finalization_incarnation_id']


def test_processing_upsert_preserves_server_owned_incarnation(monkeypatch):
    existing = {
        'id': 'conversation-1',
        'finalization_incarnation_id': 'incarnation-existing',
        'data_protection_level': 'standard',
    }
    ref = _ConversationRef(_Snapshot(existing))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    conversations_db.upsert_conversation_with_lifecycle(
        'user-1',
        {
            'id': 'conversation-1',
            'finalization_incarnation_id': 'incarnation-untrusted',
            'data_protection_level': 'standard',
        },
    )

    assert ref.set_calls[0][0]['finalization_incarnation_id'] == 'incarnation-existing'


def test_same_id_recreation_receives_a_new_incarnation(monkeypatch):
    first_ref = _ConversationRef(_Snapshot(None, exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(first_ref))
    conversations_db.create_conversation_if_absent_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'data_protection_level': 'standard'},
    )
    first_incarnation = first_ref.create_calls[0]['finalization_incarnation_id']

    recreated_ref = _ConversationRef(_Snapshot(None, exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(recreated_ref))
    conversations_db.create_conversation_if_absent_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'data_protection_level': 'standard'},
    )

    assert recreated_ref.create_calls[0]['finalization_incarnation_id'] != first_incarnation


@pytest.mark.parametrize(
    ('finalization_job_id', 'finalization_revision'),
    ((None, None), ('job-1', 4)),
    ids=('fully-legacy', 'legacy-with-job-binding'),
)
def test_ensure_finalization_identity_stamps_legacy_row_and_preserves_job_binding(
    finalization_job_id,
    finalization_revision,
):
    existing = {'id': 'conversation-1', 'data_protection_level': 'standard'}
    if finalization_job_id is not None:
        existing['finalization_job_id'] = finalization_job_id
        existing['finalization_revision'] = finalization_revision
    ref = _ConversationRef(_Snapshot(existing))

    identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=_Firestore(ref),
    )

    assert identity is not None
    assert isinstance(identity[0], str)
    assert identity[0]
    assert identity[1:] == (finalization_job_id, finalization_revision)
    assert ref.update_calls == [{'finalization_incarnation_id': identity[0]}]


def test_ensure_finalization_identity_restarts_expired_transaction_with_fresh_id(monkeypatch):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1', 'data_protection_level': 'standard'}))
    transactions = []

    class _RetryFirestore(_Firestore):
        def transaction(self):
            transaction = super().transaction()
            transactions.append(transaction)
            return transaction

    attempts = 0

    def expire_once(function):
        def invoke(transaction):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise InvalidArgument('400 The referenced transaction has expired or is no longer valid.')
            return function(transaction)

        return invoke

    monkeypatch.setattr(finalization_identity_db.firestore, 'transactional', expire_once)

    identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=_RetryFirestore(ref),
    )

    assert identity is not None
    assert attempts == 2
    assert len(transactions) == 2
    assert transactions[0] is not transactions[1]
    assert ref.update_calls == [{'finalization_incarnation_id': identity[0]}]


@pytest.mark.parametrize(
    'identity_fields',
    (
        {'finalization_incarnation_id': ''},
        {'finalization_job_id': 'job-1'},
        {'finalization_revision': 1},
        {'finalization_job_id': '', 'finalization_revision': 1},
        {'finalization_job_id': 'job-1', 'finalization_revision': True},
        {'finalization_job_id': 'job-1', 'finalization_revision': 0},
    ),
    ids=('empty-incarnation', 'job-only', 'revision-only', 'empty-job', 'boolean-revision', 'zero-revision'),
)
def test_ensure_finalization_identity_rejects_malformed_or_partial_binding(identity_fields):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1', 'data_protection_level': 'standard', **identity_fields}))

    identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=_Firestore(ref),
    )

    assert identity is None
    assert ref.update_calls == []


@pytest.mark.parametrize('fence', ({'deleted': True}, {'vector_cleanup_pending': True}), ids=('deleted', 'cleanup'))
def test_ensure_finalization_identity_respects_destructive_write_fences(fence):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1', 'data_protection_level': 'standard', **fence}))

    identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=_Firestore(ref),
    )

    assert identity is None
    assert ref.update_calls == []


def test_ensure_finalization_identity_respects_account_deletion_fence(monkeypatch):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1', 'data_protection_level': 'standard'}))
    monkeypatch.setattr(finalization_identity_db, 'account_deletion_blocks_writes', lambda *args, **kwargs: True)

    identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=_Firestore(ref),
    )

    assert identity is None
    assert ref.update_calls == []


def test_stamped_legacy_identity_fences_same_id_recreation(monkeypatch):
    ref = _ConversationRef(_Snapshot({'id': 'conversation-1', 'data_protection_level': 'standard'}))
    store = _Firestore(ref)
    monkeypatch.setattr(conversations_db, 'db', store)

    expected_identity = finalization_identity_db.ensure_conversation_finalization_identity(
        'user-1',
        'conversation-1',
        firestore_client=store,
    )
    assert expected_identity is not None
    ref.snapshot = _Snapshot(
        {
            'id': 'conversation-1',
            'finalization_incarnation_id': 'replacement-incarnation',
            'data_protection_level': 'standard',
        }
    )

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'},
        expected_finalization_identity=expected_identity,
    )

    assert persisted is False
    assert ref.set_calls == []


@pytest.mark.parametrize(
    'expected_identity',
    (
        (None, 'job-1', 1),
        ('incarnation-2', 'job-1', 1),
        ('incarnation-1', 'job-2', 1),
        ('incarnation-1', 'job-1', 2),
    ),
    ids=('explicit-legacy-incarnation', 'recreated-row', 'different-job', 'different-revision'),
)
def test_processing_result_rejects_a_different_finalization_identity(monkeypatch, expected_identity):
    ref = _ConversationRef(
        _Snapshot(
            {
                'id': 'conversation-1',
                'finalization_incarnation_id': 'incarnation-1',
                'finalization_job_id': 'job-1',
                'finalization_revision': 1,
                'data_protection_level': 'standard',
            }
        )
    )
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'},
        expected_finalization_identity=expected_identity,
    )

    assert persisted is False
    assert ref.set_calls == []


def test_processing_result_preserves_matching_finalization_identity(monkeypatch):
    identity = ('incarnation-1', 'job-1', 1)
    ref = _ConversationRef(
        _Snapshot(
            {
                'id': 'conversation-1',
                'finalization_incarnation_id': identity[0],
                'finalization_job_id': identity[1],
                'finalization_revision': identity[2],
                'data_protection_level': 'standard',
            }
        )
    )
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'},
        expected_finalization_identity=identity,
    )

    assert persisted is True
    assert ref.set_calls[0][0]['finalization_incarnation_id'] == identity[0]


def test_processing_result_under_legacy_identity_fence_does_not_mint_an_incarnation(monkeypatch):
    """A persist fenced against a legacy (None) incarnation must not mint one.

    Rows created before finalization_incarnation_id existed are finalized
    against the identity (None, job, revision). Minting an incarnation inside
    that fenced write would make the caller's later identity fences (the
    derived-effect checkpoint and the v2 effect boundaries) fence a healthy
    finalization, permanently retrying it.
    """
    identity = (None, 'job-1', 1)
    ref = _ConversationRef(
        _Snapshot(
            {
                'id': 'conversation-1',
                'finalization_job_id': 'job-1',
                'finalization_revision': 1,
                'data_protection_level': 'standard',
            }
        )
    )
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'user-1',
        {'id': 'conversation-1', 'status': 'completed', 'data_protection_level': 'standard'},
        expected_finalization_identity=identity,
    )

    assert persisted is True
    assert 'finalization_incarnation_id' not in ref.set_calls[0][0]


def test_create_if_absent_never_persists_firestore_revision_metadata(monkeypatch):
    ref = _ConversationRef(_Snapshot(None, exists=False))
    monkeypatch.setattr(conversations_db, 'db', _Firestore(ref))
    revision = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

    conversations_db.create_conversation_if_absent_with_lifecycle(
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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

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

    conversations_db.upsert_conversation_with_lifecycle('user-1', incoming)

    written, _ = ref.set_calls[0]
    assert written['folder_id'] == 'ai-assigned-folder'
