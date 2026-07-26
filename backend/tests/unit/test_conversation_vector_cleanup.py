"""Projected Firestore fences used by conversation vector cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from database import vector_db
from database import conversation_vector_cleanup as cleanup
from database.conversation_finalization_effects import (
    FINALIZATION_INCARNATION_FIELD,
    FINALIZATION_VECTOR_GENERATION_FIELD,
    TRANSCRIPT_VECTOR_COUNT_FIELD,
    VECTOR_CLEANUP_PENDING_FIELD,
)


class _Snapshot:
    def __init__(self, document, *, exists=True):
        self.id = document.id
        self.reference = document
        self.exists = exists
        self._data = dict(document.data)

    def to_dict(self):
        return dict(self._data)


class _Document:
    def __init__(self, document_id, data=None, *, exists=True, collection=None):
        self.id = document_id
        self.data = dict(data or {})
        self.exists = exists
        self.child_collection = collection
        self.field_paths = None

    def collection(self, name):
        assert name == 'conversations'
        return self.child_collection

    def get(self, *, transaction=None, field_paths=None):
        del transaction
        self.field_paths = field_paths
        return _Snapshot(self, exists=self.exists)


class _Collection:
    def __init__(self, documents):
        self.documents = {document.id: document for document in documents}
        self.selected_fields = None
        self.stream_calls = 0
        self.after_stream = None

    def document(self, document_id):
        return self.documents[document_id]

    def select(self, fields):
        self.selected_fields = fields
        return self

    def stream(self):
        self.stream_calls += 1
        snapshots = [_Snapshot(document) for document in self.documents.values()]
        if self.after_stream is not None:
            self.after_stream()
        return iter(snapshots)


class _Transaction:
    def __init__(self):
        self.updates = []
        self.deletes = []

    def update(self, document, values):
        self.updates.append((document, dict(values)))
        document.data.update(values)

    def delete(self, document):
        self.deletes.append(document)
        document.exists = False


class _Batch(_Transaction):
    def __init__(self):
        super().__init__()
        self.committed = False

    def commit(self):
        self.committed = True


class _Firestore:
    def __init__(self, conversations, jobs=None):
        self.conversations = conversations
        self.jobs = jobs or _Collection([])
        self.transactions = []
        self.batches = []

    def collection(self, name):
        if name == 'users':
            return _CollectionRoot(self.conversations)
        assert name == cleanup.FINALIZATION_JOBS_COLLECTION
        return self.jobs

    def transaction(self):
        transaction = _Transaction()
        self.transactions.append(transaction)
        return transaction

    def batch(self):
        batch = _Batch()
        self.batches.append(batch)
        return batch


class _CollectionRoot:
    def __init__(self, conversations):
        self.conversations = conversations

    def document(self, uid):
        return _Document(uid, collection=self.conversations)


def _generation_data():
    return {
        FINALIZATION_INCARNATION_FIELD: 'incarnation-1',
        FINALIZATION_VECTOR_GENERATION_FIELD: 'generation-1',
        TRANSCRIPT_VECTOR_COUNT_FIELD: 3,
    }


def test_account_cleanup_claim_uses_one_projected_scan_and_fences_each_source(monkeypatch):
    conversations = _Collection(
        [
            _Document('legacy'),
            _Document('generated', _generation_data() | {'transcript_segments': ['private']}),
        ]
    )
    client = _Firestore(conversations)
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    result = cleanup.claim_conversation_vector_cleanup_descriptors('uid-1', firestore_client=client)

    assert [
        (
            descriptor.conversation_id,
            descriptor.finalization_incarnation_id,
            descriptor.finalization_vector_generation_id,
            descriptor.transcript_vector_count,
        )
        for descriptor in result
    ] == [
        ('legacy', None, None, None),
        ('generated', 'incarnation-1', 'generation-1', 3),
    ]
    assert all(descriptor.cleanup_owner_token for descriptor in result)
    assert conversations.selected_fields == [
        'status',
        'discarded',
        'processing_admitted_at',
        'finalization_job_id',
        FINALIZATION_INCARNATION_FIELD,
        FINALIZATION_VECTOR_GENERATION_FIELD,
        TRANSCRIPT_VECTOR_COUNT_FIELD,
        VECTOR_CLEANUP_PENDING_FIELD,
        cleanup.VECTOR_CLEANUP_OWNER_FIELD,
        cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD,
    ]
    assert conversations.stream_calls == 1
    assert len(client.transactions) == 2
    assert all(document.data[VECTOR_CLEANUP_PENDING_FIELD] is True for document in conversations.documents.values())


def test_account_cleanup_claim_skips_ids_already_owned_by_the_fixed_point_scan(monkeypatch):
    retained = _Document('retained', _generation_data())
    newly_observed = _Document('newly-observed', _generation_data())
    conversations = _Collection([retained, newly_observed])
    client = _Firestore(conversations)
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    result = cleanup.claim_conversation_vector_cleanup_descriptors(
        'uid-1',
        exclude_conversation_ids={'retained'},
        firestore_client=client,
    )

    assert [descriptor.conversation_id for descriptor in result] == ['newly-observed']
    assert VECTOR_CLEANUP_PENDING_FIELD not in retained.data
    assert newly_observed.data[VECTOR_CLEANUP_PENDING_FIELD] is True
    assert len(client.transactions) == 1


def test_account_cleanup_claim_rereads_each_source_after_the_projected_scan(monkeypatch):
    document = _Document(
        'conversation-1',
        {
            FINALIZATION_INCARNATION_FIELD: 'incarnation-1',
            FINALIZATION_VECTOR_GENERATION_FIELD: 'generation-1',
            TRANSCRIPT_VECTOR_COUNT_FIELD: 1,
        },
    )
    conversations = _Collection([document])
    conversations.after_stream = lambda: document.data.update(
        {
            FINALIZATION_VECTOR_GENERATION_FIELD: 'generation-2',
            TRANSCRIPT_VECTOR_COUNT_FIELD: 4,
        }
    )
    client = _Firestore(conversations)
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    result = cleanup.claim_conversation_vector_cleanup_descriptors('uid-1', firestore_client=client)

    assert len(result) == 1
    assert result[0].conversation_id == 'conversation-1'
    assert result[0].finalization_incarnation_id == 'incarnation-1'
    assert result[0].finalization_vector_generation_id == 'generation-2'
    assert result[0].transcript_vector_count == 4
    assert result[0].cleanup_owner_token
    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True


def test_account_cleanup_releases_partial_claims_for_an_immediate_retry(monkeypatch):
    first = _Document('conversation-1', _generation_data())
    second = _Document(
        'conversation-2',
        _generation_data() | {'finalization_job_id': 'job-2'},
    )
    jobs = _Collection([_Document('job-2', {'status': 'leased', 'fanout_status': 'leased'})])
    client = _Firestore(_Collection([first, second]), jobs)
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(cleanup.ConversationVectorCleanupBusy):
        cleanup.claim_conversation_vector_cleanup_descriptors('uid-1', firestore_client=client)

    for document in (first, second):
        assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True
        assert not isinstance(document.data.get(cleanup.VECTOR_CLEANUP_OWNER_FIELD), str)

    jobs.documents['job-2'].data.update({'status': 'completed', 'fanout_status': 'fenced'})
    descriptors = cleanup.claim_conversation_vector_cleanup_descriptors('uid-1', firestore_client=client)

    assert [descriptor.conversation_id for descriptor in descriptors] == ['conversation-1', 'conversation-2']


def test_single_cleanup_claim_projects_generation_and_fences_finalization(monkeypatch):
    document = _Document('conversation-1', _generation_data())
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    result = cleanup.claim_conversation_vector_cleanup_descriptor(
        'uid-1',
        'conversation-1',
        firestore_client=client,
    )

    assert result is not None
    assert result.conversation_id == 'conversation-1'
    assert result.finalization_incarnation_id == 'incarnation-1'
    assert result.finalization_vector_generation_id == 'generation-1'
    assert result.transcript_vector_count == 3
    assert result.cleanup_owner_token
    assert document.field_paths == [
        'status',
        'discarded',
        'processing_admitted_at',
        'finalization_job_id',
        FINALIZATION_INCARNATION_FIELD,
        FINALIZATION_VECTOR_GENERATION_FIELD,
        TRANSCRIPT_VECTOR_COUNT_FIELD,
        VECTOR_CLEANUP_PENDING_FIELD,
        cleanup.VECTOR_CLEANUP_OWNER_FIELD,
        cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD,
    ]
    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True


def test_cleanup_claim_is_exclusive_and_a_released_attempt_can_retry(monkeypatch):
    document = _Document('conversation-1', _generation_data())
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    first = cleanup.claim_conversation_vector_cleanup_descriptor(
        'uid-1',
        'conversation-1',
        firestore_client=client,
    )
    assert first is not None
    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_already_claimed',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert cleanup.release_conversation_vector_cleanup_descriptor(
        'uid-1',
        first,
        firestore_client=client,
    )
    second = cleanup.claim_conversation_vector_cleanup_descriptor(
        'uid-1',
        'conversation-1',
        firestore_client=client,
    )

    assert second is not None
    assert second.cleanup_owner_token != first.cleanup_owner_token
    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True


def test_expired_cleanup_owner_cannot_be_stolen_automatically(monkeypatch):
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            VECTOR_CLEANUP_PENDING_FIELD: True,
            cleanup.VECTOR_CLEANUP_OWNER_FIELD: 'old-owner',
            cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: datetime.now(timezone.utc) - timedelta(minutes=1),
        },
    )
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_already_claimed',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert document.data[cleanup.VECTOR_CLEANUP_OWNER_FIELD] == 'old-owner'


def test_operator_force_release_requires_confirmed_termination(monkeypatch):
    client = _Firestore(_Collection([_Document('conversation-1', _generation_data())]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(ValueError, match='confirmed_worker_terminated must be true'):
        cleanup.force_release_expired_conversation_vector_cleanup_after_confirmed_termination(
            'uid-1',
            'conversation-1',
            expected_finalization_incarnation_id='incarnation-1',
            expected_cleanup_owner_token='old-owner',
            confirmed_worker_terminated=False,
            firestore_client=client,
        )

    assert client.transactions == []


def test_operator_force_release_rejects_a_live_owner():
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            VECTOR_CLEANUP_PENDING_FIELD: True,
            cleanup.VECTOR_CLEANUP_OWNER_FIELD: 'owner-1',
            cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: datetime.now(timezone.utc) + timedelta(minutes=1),
        },
    )
    transaction = _Transaction()

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_owner_still_active',
    ):
        cleanup._force_release_expired_conversation_vector_cleanup_txn(
            transaction,
            document,
            'incarnation-1',
            'owner-1',
            datetime.now(timezone.utc),
        )

    assert transaction.updates == []


def test_operator_force_release_rejects_a_same_id_replacement():
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            FINALIZATION_INCARNATION_FIELD: 'replacement-incarnation',
            VECTOR_CLEANUP_PENDING_FIELD: True,
            cleanup.VECTOR_CLEANUP_OWNER_FIELD: 'owner-1',
            cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: datetime.now(timezone.utc) - timedelta(minutes=1),
        },
    )
    transaction = _Transaction()

    with pytest.raises(
        cleanup.ConversationVectorCleanupConflict,
        match='conversation_vector_cleanup_incarnation_changed',
    ):
        cleanup._force_release_expired_conversation_vector_cleanup_txn(
            transaction,
            document,
            'incarnation-1',
            'owner-1',
            datetime.now(timezone.utc),
        )

    assert transaction.updates == []


def test_operator_force_release_is_fenced_to_the_exact_expired_owner():
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            VECTOR_CLEANUP_PENDING_FIELD: True,
            cleanup.VECTOR_CLEANUP_OWNER_FIELD: 'owner-1',
            cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: datetime.now(timezone.utc) - timedelta(minutes=1),
        },
    )
    wrong_owner_transaction = _Transaction()
    assert (
        cleanup._force_release_expired_conversation_vector_cleanup_txn(
            wrong_owner_transaction,
            document,
            'incarnation-1',
            'replacement-owner',
            datetime.now(timezone.utc),
        )
        is False
    )
    assert wrong_owner_transaction.updates == []

    transaction = _Transaction()
    assert cleanup._force_release_expired_conversation_vector_cleanup_txn(
        transaction,
        document,
        'incarnation-1',
        'owner-1',
        datetime.now(timezone.utc),
    )
    assert transaction.updates == [
        (
            document,
            {
                cleanup.VECTOR_CLEANUP_OWNER_FIELD: cleanup.firestore.DELETE_FIELD,
                cleanup.VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: cleanup.firestore.DELETE_FIELD,
            },
        )
    ]


@pytest.mark.parametrize('plan_version', (None, 2))
def test_cleanup_claim_marks_then_rejects_an_active_fanout(monkeypatch, plan_version):
    document = _Document(
        'conversation-1',
        _generation_data() | {'finalization_job_id': 'job-1'},
    )
    job_data = {'status': 'leased', 'fanout_status': 'leased'}
    if plan_version is not None:
        job_data['fanout_plan_version'] = plan_version
    client = _Firestore(_Collection([document]), _Collection([_Document('job-1', job_data)]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_fanout_active',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True
    assert len(client.transactions[0].updates) == 1


def test_cleanup_claim_keeps_an_expired_v2_writer_fenced(monkeypatch):
    document = _Document(
        'conversation-1',
        _generation_data() | {'finalization_job_id': 'job-1'},
    )
    job = _Document(
        'job-1',
        {
            'status': 'leased',
            'fanout_status': 'leased',
            'fanout_plan_version': 2,
            'lease_expires_at': datetime.now(timezone.utc) - timedelta(minutes=1),
        },
    )
    client = _Firestore(_Collection([document]), _Collection([job]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_fanout_active',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True


def test_cleanup_claim_keeps_an_expired_v1_writer_fenced(monkeypatch):
    document = _Document(
        'conversation-1',
        _generation_data() | {'finalization_job_id': 'job-1'},
    )
    job = _Document(
        'job-1',
        {
            'status': 'queued',
            'fanout_status': 'leased',
            'lease_expires_at': datetime.now(timezone.utc) - timedelta(minutes=1),
        },
    )
    client = _Firestore(_Collection([document]), _Collection([job]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_fanout_active',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True


def test_cleanup_claim_marks_then_rejects_a_live_pre_fanout_processor(monkeypatch):
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            'status': 'processing',
            'processing_admitted_at': datetime.now(timezone.utc),
        },
    )
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupBusy,
        match='conversation_vector_cleanup_processing_active',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            firestore_client=client,
        )

    assert document.data[VECTOR_CLEANUP_PENDING_FIELD] is True
    assert cleanup.VECTOR_CLEANUP_OWNER_FIELD not in document.data


def test_cleanup_claim_can_take_over_a_crashed_pre_fanout_processor(monkeypatch):
    document = _Document(
        'conversation-1',
        _generation_data()
        | {
            'status': 'processing',
            'processing_admitted_at': datetime.now(timezone.utc) - timedelta(days=2),
        },
    )
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    descriptor = cleanup.claim_conversation_vector_cleanup_descriptor(
        'uid-1',
        'conversation-1',
        firestore_client=client,
    )

    assert descriptor is not None
    assert document.data[cleanup.VECTOR_CLEANUP_OWNER_FIELD] == descriptor.cleanup_owner_token


def test_cleanup_claim_rejects_a_same_id_replacement_before_marking_it(monkeypatch):
    document = _Document('conversation-1', _generation_data())
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    with pytest.raises(
        cleanup.ConversationVectorCleanupConflict,
        match='conversation_vector_cleanup_incarnation_changed',
    ):
        cleanup.claim_conversation_vector_cleanup_descriptor(
            'uid-1',
            'conversation-1',
            expected_finalization_incarnation_id='old-incarnation',
            firestore_client=client,
        )

    assert VECTOR_CLEANUP_PENDING_FIELD not in document.data
    assert client.transactions[0].updates == []


def test_missing_conversation_has_no_cleanup_authority(monkeypatch):
    document = _Document('conversation-1', exists=False)
    client = _Firestore(_Collection([document]))
    monkeypatch.setattr(cleanup.firestore, 'transactional', lambda function: function)

    result = cleanup.claim_conversation_vector_cleanup_descriptor(
        'uid-1',
        'conversation-1',
        firestore_client=client,
    )

    assert result is None
    assert client.transactions[0].updates == []


def test_claimed_delete_purges_captured_vectors_before_source_removal(monkeypatch):
    calls = []
    descriptor = cleanup.ConversationVectorCleanupDescriptor(
        'conversation-1',
        'incarnation-1',
        'generation-1',
        2,
        'owner-1',
    )
    monkeypatch.setattr(
        vector_db,
        'delete_vector',
        lambda uid, conversation_id, generation, **kwargs: calls.append(
            ('structured', uid, conversation_id, generation, kwargs)
        ),
    )
    monkeypatch.setattr(
        vector_db,
        'delete_transcript_chunk_vectors',
        lambda uid, conversation_id, **kwargs: calls.append(('transcript', uid, conversation_id, kwargs)),
    )
    monkeypatch.setattr(
        cleanup,
        '_delete_claimed_conversation_document',
        lambda uid, claimed, **_kwargs: calls.append(('source', uid, claimed)) or True,
    )
    monkeypatch.setattr(cleanup, '_validate_claimed_conversation_source', lambda *_args, **_kwargs: True)

    assert (
        cleanup.delete_claimed_conversation_source(
            'uid-1',
            descriptor,
            delete_source_artifacts=lambda uid, conversation_id: calls.append(('artifacts', uid, conversation_id)),
        )
        is True
    )

    assert calls == [
        (
            'structured',
            'uid-1',
            'conversation-1',
            'generation-1',
            {'require_index': True},
        ),
        (
            'transcript',
            'uid-1',
            'conversation-1',
            {
                'finalization_vector_generation_id': 'generation-1',
                'transcript_vector_count': 2,
                'raise_on_failure': True,
                'require_index': True,
            },
        ),
        ('artifacts', 'uid-1', 'conversation-1'),
        ('source', 'uid-1', descriptor),
    ]


def test_claimed_delete_keeps_the_source_when_required_vector_cleanup_fails(monkeypatch):
    descriptor = cleanup.ConversationVectorCleanupDescriptor(
        'conversation-1',
        'incarnation-1',
        'generation-1',
        2,
        'owner-1',
    )
    monkeypatch.setattr(vector_db, 'delete_vector', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        vector_db,
        'delete_transcript_chunk_vectors',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('vector cleanup failed')),
    )
    delete_source = []
    monkeypatch.setattr(
        cleanup,
        '_delete_claimed_conversation_document',
        lambda *_args, **_kwargs: delete_source.append(True),
    )
    monkeypatch.setattr(cleanup, '_validate_claimed_conversation_source', lambda *_args, **_kwargs: True)
    release = []
    monkeypatch.setattr(
        cleanup,
        'release_conversation_vector_cleanup_descriptor',
        lambda uid, claimed, **_kwargs: release.append((uid, claimed)) or True,
    )

    with pytest.raises(RuntimeError, match='vector cleanup failed'):
        cleanup.delete_claimed_conversation_source(
            'uid-1',
            descriptor,
            delete_source_artifacts=lambda *_args: None,
        )

    assert delete_source == []
    assert release == [('uid-1', descriptor)]


def test_claimed_delete_revalidates_ownership_between_vector_namespaces(monkeypatch):
    descriptor = cleanup.ConversationVectorCleanupDescriptor(
        'conversation-1',
        'incarnation-1',
        'generation-1',
        2,
        'owner-1',
    )
    structured_deletes = []
    transcript_deletes = []
    source_deletes = []
    validations = iter((True, cleanup.ConversationVectorCleanupConflict('cleanup owner changed')))

    def validate(*_args, **_kwargs):
        result = next(validations)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cleanup, '_validate_claimed_conversation_source', validate)
    monkeypatch.setattr(
        vector_db,
        'delete_vector',
        lambda *_args, **_kwargs: structured_deletes.append(True),
    )
    monkeypatch.setattr(
        vector_db,
        'delete_transcript_chunk_vectors',
        lambda *_args, **_kwargs: transcript_deletes.append(True),
    )
    monkeypatch.setattr(
        cleanup,
        '_delete_claimed_conversation_document',
        lambda *_args, **_kwargs: source_deletes.append(True),
    )
    monkeypatch.setattr(
        cleanup,
        'release_conversation_vector_cleanup_descriptor',
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(cleanup.ConversationVectorCleanupConflict, match='cleanup owner changed'):
        cleanup.delete_claimed_conversation_source(
            'uid-1',
            descriptor,
            delete_source_artifacts=lambda *_args: None,
        )

    assert structured_deletes == [True]
    assert transcript_deletes == []
    assert source_deletes == []


def test_claimed_delete_keeps_source_retryable_when_playback_cleanup_fails(monkeypatch):
    descriptor = cleanup.ConversationVectorCleanupDescriptor(
        'conversation-1',
        'incarnation-1',
        'generation-1',
        2,
        'owner-1',
    )
    monkeypatch.setattr(vector_db, 'delete_vector', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vector_db, 'delete_transcript_chunk_vectors', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cleanup, '_validate_claimed_conversation_source', lambda *_args, **_kwargs: True)
    source_deletes = []
    monkeypatch.setattr(
        cleanup,
        '_delete_claimed_conversation_document',
        lambda *_args, **_kwargs: source_deletes.append(True),
    )
    releases = []
    monkeypatch.setattr(
        cleanup,
        'release_conversation_vector_cleanup_descriptor',
        lambda uid, claimed, **_kwargs: releases.append((uid, claimed)) or True,
    )

    with pytest.raises(RuntimeError, match='playback storage unavailable'):
        cleanup.delete_claimed_conversation_source(
            'uid-1',
            descriptor,
            delete_source_artifacts=lambda *_args: (_ for _ in ()).throw(RuntimeError('playback storage unavailable')),
        )

    assert source_deletes == []
    assert releases == [('uid-1', descriptor)]


def test_claimed_delete_revalidates_exact_owner_after_playback_cleanup(monkeypatch):
    descriptor = cleanup.ConversationVectorCleanupDescriptor(
        'conversation-1',
        'incarnation-1',
        'generation-1',
        2,
        'owner-1',
    )
    validations = iter(
        (
            True,
            True,
            True,
            cleanup.ConversationVectorCleanupConflict('cleanup owner changed'),
        )
    )

    def validate(*_args, **_kwargs):
        result = next(validations)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cleanup, '_validate_claimed_conversation_source', validate)
    monkeypatch.setattr(vector_db, 'delete_vector', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(vector_db, 'delete_transcript_chunk_vectors', lambda *_args, **_kwargs: None)
    playback_deletes = []
    source_deletes = []
    monkeypatch.setattr(
        cleanup,
        '_delete_claimed_conversation_document',
        lambda *_args, **_kwargs: source_deletes.append(True),
    )
    monkeypatch.setattr(
        cleanup,
        'release_conversation_vector_cleanup_descriptor',
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(cleanup.ConversationVectorCleanupConflict, match='cleanup owner changed'):
        cleanup.delete_claimed_conversation_source(
            'uid-1',
            descriptor,
            delete_source_artifacts=lambda uid, conversation_id: playback_deletes.append((uid, conversation_id)),
        )

    assert playback_deletes == [('uid-1', 'conversation-1')]
    assert source_deletes == []


def test_claimed_parent_delete_rejects_a_same_id_replacement():
    replacement = _Document(
        'conversation-1',
        {
            FINALIZATION_INCARNATION_FIELD: 'incarnation-2',
            VECTOR_CLEANUP_PENDING_FIELD: True,
        },
    )
    transaction = _Transaction()

    with pytest.raises(cleanup.ConversationVectorCleanupConflict, match='conversation_delete_incarnation_changed'):
        cleanup._delete_claimed_conversation_parent_txn(
            transaction,
            replacement,
            'incarnation-1',
            'owner-1',
        )

    assert transaction.deletes == []
    assert replacement.exists is True


def test_claimed_parent_delete_requires_the_cleanup_marker():
    source = _Document(
        'conversation-1',
        {FINALIZATION_INCARNATION_FIELD: 'incarnation-1'},
    )
    transaction = _Transaction()

    with pytest.raises(
        cleanup.ConversationVectorCleanupConflict,
        match='conversation_delete_cleanup_not_claimed',
    ):
        cleanup._delete_claimed_conversation_parent_txn(
            transaction,
            source,
            'incarnation-1',
            'owner-1',
        )

    assert transaction.deletes == []
