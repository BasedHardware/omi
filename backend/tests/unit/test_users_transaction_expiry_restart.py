"""An expired Firestore transaction must not kill a person/profile/deletion write.

Firestore retires transaction ids under load. A ``@firestore.transactional``
callable replayed by the SDK on commit contention reuses the *same* id, so once
Firestore has retired it the commit dies with ``InvalidArgument: 400 The
referenced transaction has expired or is no longer valid`` and nothing was
written. The conversation, recording-session, and finalization writers already
restart on a fresh transaction through ``run_transactional``
(``database/_client.py``); the ``database/users.py`` writers — speech-profile
teaching, speaker-embedding recovery, BYOK enrollment, and the account-deletion
state machine — still handed the transactional body a single directly-minted
transaction, so one retirement surfaced as a failed write on the listen hot
path (prod backend-listen 2026-10-27: the same terminal ``InvalidArgument``
escaping ``arm_quiet_check`` and conversation-create siblings ×80/30m inside
the uvicorn ``run_asgi`` traceback bucket).

Every test here drives the module's public wrapper (not the ``@transactional``
body) through a real expired commit and asserts the write lands on a *fresh*
transaction id, in the same spirit as
``test_conversation_persistence_transaction_expiry.py``.

Failure-Class: FC-expired-transaction-id-kills-single-minted-transactional-writer
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument
from google.cloud import firestore

from database import users as users_db

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid.'
DOCUMENT_SIZE_MESSAGE = 'document size exceeds the maximum allowed size'


class _FakeSnapshot:
    def __init__(self, data: Dict[str, Any] | None):
        self._data = data
        self.exists = data is not None
        self.id = 'doc-1'

    def to_dict(self) -> Dict[str, Any] | None:
        import copy

        return copy.deepcopy(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client
        self.id = 'doc-1'

    def get(self, transaction=None) -> _FakeSnapshot:
        if self._client.read_errors:
            raise self._client.read_errors.pop(0)
        return _FakeSnapshot(self._client.document_data)

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return _FakeCollectionReference(self._client)

    def update(self, payload: Dict[str, Any]) -> None:
        self._client.writes.append(('update', payload))

    def set(self, payload: Dict[str, Any], merge: bool = False) -> None:
        self._client.writes.append(('set', payload))


class _FakeCollectionReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client

    def document(self, _document_id: str) -> _FakeDocumentReference:
        return self._client.doc_ref

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return self


class _FakeTransaction:
    """Surface ``_Transactional.__call__`` drives on a real transaction."""

    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_FakeFirestoreClient', index: int):
        self._client = client
        self._id = f'txn-{index}'.encode()
        self.payload: Dict[str, Any] | None = None
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id=None) -> None:
        pass

    def _rollback(self) -> None:
        self.rolled_back = True

    def set(self, _doc_ref: Any, payload: Dict[str, Any], merge: bool = False) -> None:
        self.payload = payload

    def update(self, _doc_ref: Any, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def get(self, doc_ref: Any) -> '_FakeSnapshot':
        return doc_ref.get()

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        self._client.commits.append(self.payload)


class _FakeFirestoreClient:
    def __init__(
        self,
        document: Dict[str, Any] | None = None,
        commit_errors: List[BaseException] | None = None,
        read_errors: List[BaseException] | None = None,
    ):
        self.document_data = document
        self.read_errors = list(read_errors or [])
        self.commit_errors = list(commit_errors or [])
        self.commits: List[Dict[str, Any] | None] = []
        self.writes: List[tuple[str, Dict[str, Any]]] = []
        self.transactions: List[_FakeTransaction] = []
        self.doc_ref = _FakeDocumentReference(self)

    def collection(self, _collection_id: str) -> _FakeCollectionReference:
        return _FakeCollectionReference(self)

    def document(self, _document_path: str) -> _FakeDocumentReference:
        return self.doc_ref

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def _expire_once(client: _FakeFirestoreClient) -> None:
    """Queue one terminal expired-id commit ahead of success."""
    client.commit_errors.append(InvalidArgument(EXPIRED_MESSAGE))


def _install_client(monkeypatch: pytest.MonkeyPatch, client: _FakeFirestoreClient) -> None:
    monkeypatch.setattr(users_db, 'db', client)
    monkeypatch.setattr(users_db, 'account_deletion_firestore_client', lambda: client)
    monkeypatch.setattr(users_db, 'get_data_plane_firestore_client', lambda: client)


PERSON_UPDATED_AT = '2026-10-26T00:00:00+00:00'


def _person_document() -> Dict[str, Any]:
    return {
        'speech_samples': ['gs://bucket/old-sample.wav'],
        'speech_sample_transcripts': ['hello'],
        'speaker_embedding': [0.1],
        'updated_at': PERSON_UPDATED_AT,
        'save_other_voice_profiles': True,
    }


def test_add_person_speech_sample_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(_person_document(), [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    added = users_db.add_person_speech_sample('uid-1', 'person-1', 'gs://bucket/new-sample.wav', 'hi')

    assert added is True
    assert len(client.transactions) == 2, 'the retry must use a fresh transaction, not the retired id'
    assert client.transactions[0].rolled_back is True
    assert len(client.commits) == 1
    assert client.commits[0]['speech_samples'] == [
        'gs://bucket/old-sample.wav',
        'gs://bucket/new-sample.wav',
    ]


def test_remove_person_speech_sample_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    document = _person_document()
    client = _FakeFirestoreClient(document, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    removed = users_db.remove_person_speech_sample('uid-1', 'person-1', 'gs://bucket/old-sample.wav')

    assert removed is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['speech_samples'] == []
    assert client.commits[0]['speech_sample_transcripts'] == []
    assert client.commits[0]['speaker_embedding'] is None


def test_replace_person_speech_profile_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(_person_document(), [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)
    monkeypatch.setattr(users_db, 'person_teaching_authorized', lambda *args, **kwargs: True)

    old_samples = users_db.replace_person_speech_profile(
        'uid-1',
        'person-1',
        PERSON_UPDATED_AT,
        'gs://bucket/taught.wav',
        'taught words',
        [0.9, 0.8],
        'conversation-1',
        ['segment-1'],
    )

    assert old_samples == ['gs://bucket/old-sample.wav']
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    written = client.commits[0]
    assert written['speech_samples'] == ['gs://bucket/taught.wav']
    assert written['speaker_embedding'] == [0.9, 0.8]


def test_set_person_speaker_embedding_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(_person_document(), [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)
    monkeypatch.setattr(users_db, 'person_teaching_authorized', lambda *args, **kwargs: True)

    recovered = users_db.set_person_speaker_embedding(
        'uid-1', 'person-1', [0.7, 0.6], expected_updated_at=PERSON_UPDATED_AT
    )

    assert recovered is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['speaker_embedding'] == [0.7, 0.6]


def test_invalidate_person_speech_profile_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    document = _person_document()
    document['speech_sample_source'] = {'conversation_id': 'conversation-1', 'segment_ids': ['segment-1']}
    client = _FakeFirestoreClient(document, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    removed = users_db.invalidate_person_speech_profile('uid-1', 'person-1', 'conversation-1', ['segment-1'])

    assert removed == ['gs://bucket/old-sample.wav']
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    written = client.commits[0]
    assert written['speech_samples'] == []
    assert written['speaker_embedding'] is None


def test_set_byok_active_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'byok': {'fingerprints': {'legacy': {}}}}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    users_db.set_byok_active('uid-1', {'openai': {'k': 'v'}})

    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    written = client.commits[0]['byok']
    assert written['active'] is True
    assert written['fingerprints']['openai'] == {'k': 'v'}
    assert written['fingerprints']['legacy'] is firestore.DELETE_FIELD


def test_mark_user_deletion_wipe_intent_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(None, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    intent = users_db.mark_user_deletion_wipe_intent('uid-1')

    assert intent['dispatch_claimed'] is True
    assert isinstance(intent['wipe_job_id'], str) and intent['wipe_job_id']
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    # The replayed body re-rolls the job id; the committed id must be the
    # returned one, not the first attempt's retired draft.
    assert client.commits[0]['wipe_job_id'] == intent['wipe_job_id']
    assert client.commits[0]['wipe_status'] == 'pending'


def test_mark_user_deletion_wipe_started_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(
        {'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    started = users_db.mark_user_deletion_wipe_started('uid-1', 'job-1')

    assert started is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['wipe_status'] == 'pending'


def test_mark_user_deletion_wipe_completed_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'pending'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    completed = users_db.mark_user_deletion_wipe_completed('uid-1')

    assert completed is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['wipe_status'] == 'completed'


def test_mark_user_deletion_billing_failed_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'running'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    parked = users_db.mark_user_deletion_billing_failed('uid-1', 'sub_1', 'card declined')

    assert parked is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    written = client.commits[0]
    assert written['wipe_status'] == 'billing_failed'
    assert written['billing_subscription_id'] == 'sub_1'


def test_heartbeat_user_deletion_wipe_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'running'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    users_db.heartbeat_user_deletion_wipe('uid-1')

    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert 'wipe_running_at' in client.commits[0]


def test_claim_deletion_wipe_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'failed'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    claimed = users_db.claim_deletion_wipe('uid-1')

    assert claimed == 'doc-1', 'the claim returns the claimed document id (the uid)'
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['wipe_status'] == 'retrying'


def test_claim_deletion_wipe_for_task_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'pending'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    claimed = users_db.claim_deletion_wipe_for_task('uid-1')

    assert claimed == 'claimed'
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['wipe_status'] == 'retrying'


def test_ensure_deletion_wipe_job_id_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'pending'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    wipe_job_id = users_db.ensure_deletion_wipe_job_id('uid-1')

    assert isinstance(wipe_job_id, str) and len(wipe_job_id) == 32
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['wipe_job_id'] == wipe_job_id


def test_record_late_agent_vm_cleanup_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient({'wipe_status': 'deleting_auth'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    recorded = users_db.record_late_agent_vm_cleanup('uid-1', 'vm-1', 'us-east1', '12345')

    assert recorded is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['late_agent_vm_cleanup']['vmName'] == 'vm-1'


def test_adopt_legacy_late_agent_vm_cleanup_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(
        {
            'wipe_status': 'deleting_auth',
            'late_agent_vm_cleanup': {'vmName': 'vm-1', 'zone': 'us-east1'},
        },
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    adopted = users_db.adopt_legacy_late_agent_vm_cleanup('uid-1', 'vm-1', 'us-east1', '12345')

    assert adopted is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    assert client.commits[0]['late_agent_vm_cleanup.expectedInstanceId'] == '12345'


def test_permanent_invalid_argument_is_never_replayed(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(_person_document(), [InvalidArgument(DOCUMENT_SIZE_MESSAGE)])
    _install_client(monkeypatch, client)

    with pytest.raises(InvalidArgument):
        users_db.add_person_speech_sample('uid-1', 'person-1', 'gs://bucket/new-sample.wav', 'hi')

    assert len(client.transactions) == 1, 'only the expired-id shape may restart'
    assert client.commits == []


def test_permanently_expiring_transaction_stops_after_budget(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(
        _person_document(),
        [InvalidArgument(EXPIRED_MESSAGE) for _ in range(10)],
    )
    _install_client(monkeypatch, client)

    with pytest.raises(InvalidArgument):
        users_db.add_person_speech_sample('uid-1', 'person-1', 'gs://bucket/new-sample.wav', 'hi')

    assert len(client.transactions) == 3, 'the restart budget must stay bounded'
    assert client.commits == []


def test_run_transactional_honors_initial_transaction():
    client = _FakeFirestoreClient({'wipe_status': 'pending'})
    transaction = client.transaction()

    result = users_db.run_transactional(
        client,
        lambda txn: users_db._claim_deletion_wipe_task_txn(txn, client.doc_ref, __import__('datetime').timedelta(0)),
        initial_transaction=transaction,
    )

    assert result == 'claimed'
    assert client.transactions == [transaction], 'the caller-owned transaction must be attempt one'
    assert len(client.commits) == 1


def test_replace_fence_denial_is_preserved_across_expiry(monkeypatch: pytest.MonkeyPatch):
    """An expired attempt must not launder a denial the replay re-evaluates."""
    client = _FakeFirestoreClient(
        {**_person_document(), 'save_other_voice_profiles': False},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    result = users_db.set_person_speaker_embedding('uid-1', 'person-1', [0.7], expected_updated_at=PERSON_UPDATED_AT)

    assert result is False
    assert len(client.transactions) == 2, 'expiry still restarts — the fence, not the id, decides'
    assert all(
        not payload or 'speaker_embedding' not in payload for payload in client.commits
    ), 'the replay must re-deny, never launder the write through the restart'


def test_streaming_read_abort_409_is_also_restarted(monkeypatch: pytest.MonkeyPatch):
    """The same retirement surfaces as Aborted 409 on the transactional read.

    The SDK's ``_Transactional.__call__`` replays a *commit*-side ``Aborted``
    itself on the same id; the read-side 409 (raised from the body, before any
    commit) is what propagates to ``run_transactional`` — so this queue puts
    the error on the body's read, matching the documented shape.
    """
    client = _FakeFirestoreClient(_person_document(), read_errors=[Aborted(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    added = users_db.add_person_speech_sample('uid-1', 'person-1', 'gs://bucket/new-sample.wav', 'hi')

    assert added is True
    assert len(client.transactions) == 2, 'the read-path retirement needs a fresh id just like the commit'
    assert len(client.commits) == 1
    assert client.commits[0]['speech_samples'][-1] == 'gs://bucket/new-sample.wav'


def test_unrelated_aborted_never_restarts(monkeypatch: pytest.MonkeyPatch):
    """Only the retirement message restarts; plain contention keeps the SDK's own budget."""
    client = _FakeFirestoreClient(_person_document(), read_errors=[Aborted('database label already in use')])
    _install_client(monkeypatch, client)

    with pytest.raises(Exception):
        users_db.add_person_speech_sample('uid-1', 'person-1', 'gs://bucket/new-sample.wav', 'hi')

    assert len(client.transactions) == 1
    assert client.commits == []


def test_listen_onboarding_admission_survives_expired_transaction(monkeypatch: pytest.MonkeyPatch):
    """The admission arm on the listen session create path restarts on expiry."""
    client = _FakeFirestoreClient({'onboarding': {}}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    admitted = users_db.ensure_backend_onboarding_admission('uid-1')

    assert admitted is True
    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    written = client.commits[0]
    assert written['status'] == 'active'
    assert len(written['session_id']) >= 16


def test_deletion_intent_expiry_never_moves_completed_backwards(monkeypatch: pytest.MonkeyPatch):
    """A replayed intent must still join, not reset, a completed wipe."""
    document = {'wipe_status': 'completed', 'wipe_job_id': 'job-done'}
    client = _FakeFirestoreClient(document, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    intent = users_db.mark_user_deletion_wipe_intent('uid-1')

    assert intent == {'wipe_job_id': 'job-done', 'dispatch_claimed': False}
    assert len(client.transactions) == 2
    joined = [payload for payload in client.commits if payload]
    assert joined == [], 'a completed wipe is joined, never rewritten by a replayed intent'


def test_started_expiry_never_promotes_foreign_job(monkeypatch: pytest.MonkeyPatch):
    """A replayed start must still refuse a job id it does not own."""
    client = _FakeFirestoreClient(
        {'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    started = users_db.mark_user_deletion_wipe_started('uid-1', 'job-2')

    assert started is False
    assert len(client.transactions) == 2
    assert all(not payload for payload in client.commits), 'the fence, not the restart, decides'


def test_task_claim_expiry_never_claims_fresh_running_wipe(monkeypatch: pytest.MonkeyPatch):
    """A replayed task claim must still respect a fresh running lease."""
    now = users_db.datetime.now(users_db.timezone.utc)
    client = _FakeFirestoreClient(
        {'wipe_status': 'running', 'wipe_running_at': now},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    claimed = users_db.claim_deletion_wipe_for_task('uid-1', running_stale_after=timedelta(minutes=10))

    assert claimed == 'running'
    assert len(client.transactions) == 2
    assert all(not payload for payload in client.commits), 'a live lease is not stolen across a restart'


def test_byok_expiry_prunes_removed_fingerprints_exactly_once(monkeypatch: pytest.MonkeyPatch):
    """The replayed enrollment re-derives the fingerprint diff from the same snapshot."""
    client = _FakeFirestoreClient(
        {'byok': {'fingerprints': {'legacy': {}, 'openai': {}}}},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    users_db.set_byok_active('uid-1', {'openai': {'k': 'v'}})

    assert len(client.transactions) == 2
    assert len(client.commits) == 1
    fingerprints = client.commits[0]['byok']['fingerprints']
    assert fingerprints['legacy'] is firestore.DELETE_FIELD
    assert 'openai' not in fingerprints or fingerprints['openai'] == {'k': 'v'}


def test_onboarding_admission_expiry_never_admits_completed_onboarding(monkeypatch: pytest.MonkeyPatch):
    """A replayed admission must still deny an onboarding completed mid-retry."""
    client = _FakeFirestoreClient({'onboarding': {'completed': True}}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    admitted = users_db.ensure_backend_onboarding_admission('uid-1')

    assert admitted is False
    assert len(client.transactions) == 2
    assert all(not payload for payload in client.commits), 'no admission is issued behind the fence'


def test_heartbeat_expiry_never_resurrects_failed_wipe(monkeypatch: pytest.MonkeyPatch):
    """A replayed heartbeat still refreshes only a live ``running`` wipe."""
    client = _FakeFirestoreClient({'wipe_status': 'failed'}, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    users_db.heartbeat_user_deletion_wipe('uid-1')

    assert len(client.transactions) == 2
    assert all(not payload for payload in client.commits), 'a failed wipe stays failed across the restart'


def test_intent_expiry_promotes_legacy_deleting_auth_with_existing_job_id(monkeypatch: pytest.MonkeyPatch):
    """A replayed intent still promotes the legacy state under the SAME job id."""
    client = _FakeFirestoreClient(
        {'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-legacy'},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    _install_client(monkeypatch, client)

    intent = users_db.mark_user_deletion_wipe_intent('uid-1')

    assert intent == {'wipe_job_id': 'job-legacy', 'dispatch_claimed': True}
    assert len(client.transactions) == 2
    written = [payload for payload in client.commits if payload]
    assert len(written) == 1
    assert written[0]['wipe_status'] == 'pending'
    assert 'wipe_job_id' not in written[0], 'the promotion never overwrites the joined job id'


def test_record_cleanup_expiry_never_records_for_unadmitted_deletion(monkeypatch: pytest.MonkeyPatch):
    """A replayed late-VM record still refuses a deletion with no admission marker."""
    client = _FakeFirestoreClient(None, [InvalidArgument(EXPIRED_MESSAGE)])
    _install_client(monkeypatch, client)

    recorded = users_db.record_late_agent_vm_cleanup('uid-1', 'vm-1', 'us-east1', '12345')

    assert recorded is False
    assert len(client.transactions) == 2
    assert all(not payload for payload in client.commits), 'no cleanup record lands behind the state fence'
