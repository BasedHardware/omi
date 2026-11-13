"""Persist-phase artifact registration replays contention inside the shared bounded budget.

The GPU worker's persist stage registers every durable artifact through
``register_batch_artifact`` — a read-write transaction over the hot segment
job and the batch privacy fence. The Firestore SDK retries commit-time
``Aborted`` on one transaction id but never a read-time abort, so the
persist phase used to fail the whole GPU unit on a commit nobody made and
the scheduler re-queued a fresh decode/VAD/ASR/diarization pass. The
completion phase hit the identical class and already replays it through
``run_retention_transaction``; these tests pin the persist phase onto the
same budget and freeze the safety envelope around the replay: fresh
transaction per attempt, per-attempt re-derivation of every lease,
privacy, retention and token window, no replay of real refusals, the
kill-switch rollback, and the worker-visible isolation of whatever still
fails.

Failure-Class: FC-persist-registration-read-abort-fails-gpu-unit-and-requeues-it
"""

import hashlib
import logging
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from config.batch_language_recovery import REPAIR_EPOCH, REPAIR_PROVIDER
from database import firestore_transaction_retry
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.firestore_transaction_retry import FirestoreContentionExhausted, transaction_retry_deadline_scope
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
)
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.retention import (
    expire_completed_segment,
    register_batch_artifact,
    run_retention_transaction,
)
from utils.batch_pipeline import retention as retention_module

UID = 'synthetic-persist-owner'
CID = 'synthetic-persist-conversation'
SEG = 'persistcont-segment'
NS = 'batch_pipeline_test_persistcont'
OWNER_KEY = privacy_owner_key(UID)
JOBS = NS + '_jobs'
ARTIFACTS = NS + '_artifacts'
RESULTS = NS + '_results'
SHADOW_JOBS = NS + '_shadow_jobs'
PRIVACY = 'batch_pipeline_privacy'
TOKEN = 'a' * 32
OTHER_TOKEN = 'b' * 32
RESULT_URI = f'gs://synthetic-bucket/results/{SEG}/{TOKEN}.enc'
UPLOAD_PENDING_SECONDS = 30 * 60
CAPTURE_TTL = 24 * 3600
FINALIZED_TTL = 3600
RECEIPT_RETENTION_DAYS = 45
ABORT_MESSAGE = 'synthetic persist registration read abort'


def artifact_id(uri=RESULT_URI, segment=SEG):
    return hashlib.sha256(f'{segment}\0{uri}'.encode()).hexdigest()


def base_rows():
    """The minimal privacy-fence read set for one owner and one conversation."""
    return {
        ('users', UID): {'data_protection_level': 'enhanced'},
        ('users', UID, 'conversations', CID): {'id': CID},
    }


def leased_rows():
    rows = base_rows()
    rows[(JOBS, SEG)] = {
        'state': 'leased',
        'owner_id': UID,
        'conversation_id': CID,
        'capture_at': 100.0,
        'duration_seconds': 10.0,
        'projection_binding': {},
    }
    return rows


def result_item():
    return WorkItem(
        SEG, UID, 100.0, 'gs://synthetic/audio#123', 10.0, Priority.FRESH, conversation_id=CID, privacy_generation=0
    )


def make_store(rows):
    return SimpleNamespace(client=StrictFirestore(rows), namespace=NS)


def register_result(store, *, uri=RESULT_URI, kind='result', item=None, generation=0):
    return register_batch_artifact(
        store, UID, SEG, uri, kind, generation, item=item if item is not None else result_item()
    )


def register_audio(store, *, uri=RESULT_URI, item=None):
    return register_batch_artifact(store, UID, SEG, uri, 'audio', 0, item=item if item is not None else result_item())


@pytest.fixture
def retry_sleeps(monkeypatch):
    """Capture the shared budget's inter-attempt sleeps with pinned jitter."""
    sleeps = []
    retry = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast_retry(*args, **kwargs):
        return retry(*args, **kwargs, sleep=sleeps.append, random_value=lambda: 0.0)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast_retry)
    return sleeps


@pytest.fixture
def instant_restarts(monkeypatch):
    """Collapse the expiry restarts' real backoff to zero for fast tests."""
    import database._client as client_module

    monkeypatch.setattr(client_module, 'equal_jitter_delay', lambda attempt, random_value=None: 0.0)


def script_reads(client, monkeypatch, *, abort=(), mutate=None, error=None):
    """Abort transactional reads on the given 1-based attempts; run ``mutate`` once per attempt.

    Attempt numbers are positions in ``client.transactions``: the shared
    budget creates one fresh transaction before each outer attempt, and the
    expiry restart creates one before each inner restart.
    """
    failure = error or Aborted(ABORT_MESSAGE)
    original = StrictFirestoreDocument.get
    fired = set()

    def get(self, transaction=None, **kwargs):
        if transaction is None:
            return original(self, **kwargs)
        attempt = len(client.transactions)
        if mutate is not None and attempt not in fired:
            fired.add(attempt)
            mutate(attempt)
        if attempt in abort:
            raise failure
        return original(self, transaction=transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)


def abort_commits(client, monkeypatch, attempts, error=None):
    """Fail the transaction commit itself on the given 1-based attempts."""
    failure = error or Aborted('synthetic persist registration commit abort')
    original = client.transaction

    def transaction(max_attempts=None):
        tx = original(max_attempts)
        if len(client.transactions) in attempts:

            def commit():
                raise failure

            tx._commit = commit
        return tx

    monkeypatch.setattr(client, 'transaction', transaction)


def test_result_register_replays_read_abort_at_job_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    returned = register_result(store)
    assert returned == artifact_id()
    assert store.client.rows[(ARTIFACTS, artifact_id())]['uri'] == RESULT_URI
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_artifact_reference_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('artifact reference abort'))
    returned = register_result(store)
    assert returned == artifact_id()
    assert (ARTIFACTS, artifact_id()) in store.client.rows
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_account_deletion_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('account deletion read abort'))
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_user_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('user read abort'))
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_privacy_generation_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('privacy generation read abort'))
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_conversation_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('conversation read abort'))
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_result_register_replays_read_abort_at_deleted_conversation_read(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, error=Aborted('deleted conversation read abort'))
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_result_register_replays_commit_abort_on_a_fresh_transaction(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    abort_commits(store.client, monkeypatch, attempts={1})
    assert register_result(store) == artifact_id()
    assert store.client.rows[(ARTIFACTS, artifact_id())]['kind'] == 'result'
    assert len(store.client.transactions) == 2


def test_expired_transaction_id_restarts_within_one_outer_attempt(retry_sleeps, instant_restarts, monkeypatch):
    store = make_store(leased_rows())
    script_reads(
        store.client,
        monkeypatch,
        abort={1},
        error=InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
    )
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2
    assert retry_sleeps == []


def test_contention_exhaustion_raises_the_shared_exhausted_envelope(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert len(store.client.transactions) == 5
    assert len(retry_sleeps) == 4


def test_exhaustion_leaves_the_artifact_collection_untouched(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_exhaustion_preserves_a_preexisting_artifact_registration(retry_sleeps, monkeypatch):
    rows = leased_rows()
    rows[(ARTIFACTS, artifact_id())] = {'uri': RESULT_URI, 'kind': 'result', 'owner_id': UID}
    store = make_store(rows)
    before = dict(store.client.rows[(ARTIFACTS, artifact_id())])
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert store.client.rows[(ARTIFACTS, artifact_id())] == before


def test_kill_switch_restores_the_bare_single_shot_commit(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with pytest.raises(Aborted):
        register_result(store)
    assert len(store.client.transactions) == 1
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_kill_switch_default_keeps_the_bounded_budget(retry_sleeps, monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', raising=False)
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_every_replay_uses_a_fresh_single_attempt_transaction(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2})
    assert register_result(store) == artifact_id()
    transactions = store.client.transactions
    assert len(transactions) == 3
    assert len({id(tx) for tx in transactions}) == 3
    assert all(tx._max_attempts == 1 for tx in transactions)


def test_replays_wait_equal_jitter_between_attempts(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4})
    assert register_result(store) == artifact_id()
    assert retry_sleeps == [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.4), pytest.approx(0.8)]


def test_jitter_is_capped_at_one_second(monkeypatch):
    store = make_store(leased_rows())
    sleeps = []
    retry = firestore_transaction_retry.run_with_transaction_contention_retry

    def capped_random_retry(*args, **kwargs):
        return retry(*args, **kwargs, sleep=sleeps.append, random_value=lambda: 1.0)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', capped_random_retry)
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4})
    assert register_result(store) == artifact_id()
    assert sleeps == [0.2, 0.4, 0.8, 1.6]


def test_recovered_outcome_is_logged_with_the_register_label(retry_sleeps, monkeypatch, caplog):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert register_result(store) == artifact_id()
    recovered = [record for record in caplog.records if 'outcome=recovered' in record.getMessage()]
    assert len(recovered) == 1
    assert 'operation=batch_artifact_register' in recovered[0].getMessage()
    assert 'attempt=2/5' in recovered[0].getMessage()


def test_exhausted_outcome_is_logged_with_the_register_label(retry_sleeps, monkeypatch, caplog):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            register_result(store)
    exhausted = [record for record in caplog.records if 'outcome=exhausted' in record.getMessage()]
    assert len(exhausted) == 1
    assert 'operation=batch_artifact_register' in exhausted[0].getMessage()
    assert 'attempt=5/5' in exhausted[0].getMessage()


def test_each_failed_attempt_logs_a_retry_outcome(retry_sleeps, monkeypatch, caplog):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2})
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert register_result(store) == artifact_id()
    retries = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(retries) == 2
    assert all('operation=batch_artifact_register' in message for message in retries)


def test_first_attempt_success_never_logs_contention(retry_sleeps, monkeypatch, caplog):
    store = make_store(leased_rows())
    with caplog.at_level(logging.DEBUG, logger='database.firestore_transaction_retry'):
        assert register_result(store) == artifact_id()
    assert not [record for record in caplog.records if 'firestore_transaction_contention' in record.getMessage()]


def test_privacy_refusal_is_never_replayed(retry_sleeps, monkeypatch):
    rows = base_rows()
    rows[(JOBS, SEG)] = {'state': 'queued', 'owner_id': UID, 'conversation_id': CID, 'projection_binding': {}}
    store = make_store(rows)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_result(store)
    assert raised.value.reason.value == 'result_lease_lost'
    assert len(store.client.transactions) == 1


def test_owner_mismatch_is_never_replayed(retry_sleeps, monkeypatch):
    rows = leased_rows()
    rows[(JOBS, SEG)]['owner_id'] = 'synthetic-other-owner'
    store = make_store(rows)
    with pytest.raises(ValueError, match='artifact owner mismatch'):
        register_result(store)
    assert len(store.client.transactions) == 1


def test_unknown_artifact_kind_fails_before_any_transaction(monkeypatch):
    store = make_store(leased_rows())
    with pytest.raises(ValueError, match='unknown artifact kind'):
        register_batch_artifact(store, UID, SEG, RESULT_URI, 'nonsense', 0, item=result_item())
    assert store.client.transactions == []


def test_result_lease_lost_is_never_replayed(retry_sleeps, monkeypatch):
    rows = base_rows()
    rows[(JOBS, SEG)] = {'state': 'queued', 'owner_id': UID, 'conversation_id': CID, 'projection_binding': {}}
    store = make_store(rows)
    script_reads(store.client, monkeypatch)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_result(store)
    assert raised.value.reason.value == 'result_lease_lost'
    assert len(store.client.transactions) == 1


def test_missing_job_audio_refusal_is_never_replayed(retry_sleeps, monkeypatch):
    store = make_store(base_rows())
    script_reads(store.client, monkeypatch)
    with pytest.raises(ValueError, match='result requires an existing owner job'):
        register_batch_artifact(store, UID, SEG, RESULT_URI, 'audio', 0, item=None)
    assert len(store.client.transactions) == 1


def test_missing_job_result_refuses_at_the_lease_gate(retry_sleeps, monkeypatch):
    """The lease gate precedes the missing-job rule: a result with no job is a lease loss."""
    store = make_store(base_rows())
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_result(store)
    assert raised.value.reason.value == 'result_lease_lost'
    assert len(store.client.transactions) == 1


def window_uri(token=TOKEN):
    return f'gs://synthetic-bucket/results/{SEG}/{token}.enc'


def window_job(window, *, token=TOKEN):
    """Job rows admitting exactly one persist write window; kind='result' otherwise refuses."""
    base = {
        'owner_id': UID,
        'conversation_id': CID,
        'capture_at': 100.0,
        'duration_seconds': 10.0,
        'projection_binding': {},
    }
    if window == 'leased':
        return {'state': 'leased', **base}
    if window == 'recovery':
        return {
            'state': 'quarantined',
            'recovery_state': 'running',
            'recovery': {'token': token, 'privacy_generation': 0, 'provider': 'modulate'},
            **base,
        }
    if window == 'disposition':
        return {
            'state': 'quarantined',
            'recovery_state': 'failed_held',
            'silence_disposition': {'state': 'prepared', 'privacy_generation': 0, 'token': token},
            **base,
        }
    if window == 'terminal':
        return {
            'state': 'quarantined',
            'recovery_state': 'held',
            'policy_parts': {'recovery': {'terminal_empty_disposition': True}},
            'terminal_disposition': {'state': 'prepared', 'privacy_generation': 0, 'token': token},
            **base,
        }
    if window == 'provider':
        return {'state': 'provider_running', 'provider_intent': {'privacy_generation': 0, 'token': token}, **base}
    if window == 'redrive':
        return {
            'state': 'quarantined',
            'recovery_state': 'held',
            'policy_parts': {'recovery': {'speech_empty_multilingual': True}},
            'speech_redrive': {'state': 'running', 'privacy_generation': 0, 'token': token, 'paid_epoch': 2},
            **base,
        }
    if window == 'redrive_language':
        return {
            'state': 'quarantined',
            'recovery_state': 'held',
            'stt_route': {'provider_reason': 'unsupported_language'},
            'policy_parts': {'recovery': {'recovery_enabled': True}},
            'recovery': {'provider': 'modulate', 'token': token, 'privacy_generation': 0},
            'speech_redrive': {
                'state': 'running',
                'privacy_generation': 0,
                'token': token,
                'paid_epoch': 3,
                'provider': 'soniox',
            },
            **base,
        }
    raise AssertionError(f'unknown window {window}')


def window_store(window, *, token=TOKEN):
    rows = base_rows()
    rows[(JOBS, SEG)] = window_job(window, token=token)
    return make_store(rows)


def register_window(store, *, uri=None, kind='result', generation=0):
    return register_batch_artifact(store, UID, SEG, uri or window_uri(), kind, generation, item=result_item())


def rotate_window_token(store, attempt):
    """Move the admitted window token after a lost attempt: the replay must refuse, not guess."""
    job = store.client.rows[(JOBS, SEG)]
    for marker in ('recovery', 'silence_disposition', 'terminal_disposition', 'provider_intent', 'speech_redrive'):
        if marker in job and isinstance(job[marker], dict) and job[marker].get('token') == TOKEN:
            job[marker]['token'] = OTHER_TOKEN


def voice_rows():
    rows = base_rows()
    rows[(JOBS, SEG)] = {
        'state': 'projected',
        'owner_id': UID,
        'conversation_id': CID,
        'capture_at': 100.0,
        'duration_seconds': 10.0,
        'projection_binding': {'owner_id': UID, 'private_cloud_sync_enabled': False},
    }
    rows[(RESULTS, SEG)] = {
        'projection_parts': {'0': {'conversation_id': CID, 'speaker_scope': 'final:batch:' + SEG}},
    }
    return rows


def voice_item(capture=None):
    return WorkItem(
        SEG,
        UID,
        time.time() - 10 if capture is None else capture,
        'gs://synthetic/audio#123',
        10.0,
        Priority.FRESH,
        conversation_id=CID,
        privacy_generation=0,
    )


VOICE_URI = f'gs://synthetic-bucket/voice_evidence/{SEG}/{TOKEN}.enc'


def register_voice(store, *, uri=VOICE_URI, item=None):
    return register_batch_artifact(
        store, UID, SEG, uri, 'voice_evidence', 0, item=item if item is not None else voice_item()
    )


def shadow_rows():
    rows = base_rows()
    rows[(SHADOW_JOBS, SEG)] = {'state': 'staging', 'owner_key': OWNER_KEY, 'shadow': True}
    return rows


def shadow_item():
    return replace(result_item(), shadow=True)


SHADOW_URI = f'gs://synthetic-bucket/audio/{SEG}/{TOKEN}.enc'


def register_shadow(store, *, uri=SHADOW_URI):
    return register_batch_artifact(store, UID, SEG, uri, 'audio', 0, item=shadow_item())


def test_reregistration_after_lost_ack_writes_nothing(monkeypatch):
    store = make_store(leased_rows())
    first = register_result(store)
    before = dict(store.client.rows[(ARTIFACTS, first)])
    sets_before = len(store.client.transactions[-1].sets)
    second = register_result(store)
    assert second == first
    assert store.client.rows[(ARTIFACTS, first)] == before
    assert len(store.client.transactions[-1].sets) == sets_before


def test_artifact_identity_is_deterministic_per_segment_and_uri(monkeypatch):
    assert artifact_id() == hashlib.sha256(f'{SEG}\0{RESULT_URI}'.encode()).hexdigest()
    other = window_uri(token=OTHER_TOKEN)
    assert artifact_id(other) != artifact_id()


def test_replay_reuses_the_same_deterministic_identity(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    assert register_result(store) == artifact_id()
    assert [path for path in store.client.rows if path[0] == ARTIFACTS] == [(ARTIFACTS, artifact_id())]


def test_commit_abort_replay_takes_the_existing_document_path(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    abort_commits(store.client, monkeypatch, attempts={1})
    assert register_result(store) == artifact_id()
    replay = store.client.transactions[-1]
    assert replay.creates == []
    assert (ARTIFACTS, artifact_id()) in store.client.rows


def test_write_pending_until_is_stamped_for_the_upload_window(monkeypatch):
    store = make_store(leased_rows())
    before = time.time()
    register_result(store)
    stamped = store.client.rows[(ARTIFACTS, artifact_id())]['write_pending_until'].timestamp()
    assert before + UPLOAD_PENDING_SECONDS - 5 <= stamped <= time.time() + UPLOAD_PENDING_SECONDS + 5


def test_audio_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    assert register_audio(store) == artifact_id()
    assert store.client.rows[(ARTIFACTS, artifact_id())]['kind'] == 'audio'


def test_voice_evidence_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1})
    assert register_voice(store) == artifact_id(VOICE_URI)
    assert store.client.rows[(ARTIFACTS, artifact_id(VOICE_URI))]['kind'] == 'voice_evidence'


def test_shadow_audio_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = make_store(shadow_rows())
    script_reads(store.client, monkeypatch, abort={1})
    assert register_shadow(store) == artifact_id(SHADOW_URI)
    registered = store.client.rows[(ARTIFACTS, artifact_id(SHADOW_URI))]
    assert registered['shadow'] is True


def test_shadow_registration_refuses_non_staging_state(retry_sleeps, monkeypatch):
    rows = shadow_rows()
    rows[(SHADOW_JOBS, SEG)]['state'] = 'projected'
    store = make_store(rows)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_shadow(store)
    assert raised.value.args[0] == 'shadow_artifact_state'
    assert len(store.client.transactions) == 1


def test_shadow_registration_refuses_foreign_owner(retry_sleeps, monkeypatch):
    rows = shadow_rows()
    rows[(SHADOW_JOBS, SEG)]['owner_key'] = privacy_owner_key('synthetic-other-owner')
    store = make_store(rows)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_shadow(store)
    assert raised.value.args[0] == 'shadow_artifact_owner'


def test_mirror_refresh_runs_once_after_the_winning_attempt(retry_sleeps, monkeypatch):
    from utils.batch_pipeline import retention as retention_module

    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    refreshes = []
    monkeypatch.setattr(retention_module, 'mirror_refresh', lambda *args, **kwargs: refreshes.append(args))
    assert register_result(store) == artifact_id()
    assert refreshes == [(NS, [('artifacts', artifact_id())])]


def test_mirror_refresh_is_skipped_when_the_budget_exhausts(retry_sleeps, monkeypatch):
    from utils.batch_pipeline import retention as retention_module

    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    refreshes = []
    monkeypatch.setattr(retention_module, 'mirror_refresh', lambda *args, **kwargs: refreshes.append(args))
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert refreshes == []


def test_audio_registration_is_allowed_in_any_job_state(monkeypatch):
    rows = base_rows()
    rows[(JOBS, SEG)] = window_job('recovery')
    store = make_store(rows)
    assert register_audio(store) == artifact_id()


def test_audio_registration_without_a_job_needs_the_matching_owner(monkeypatch):
    store = make_store(base_rows())
    assert register_audio(store) == artifact_id()
    registered = store.client.rows[(ARTIFACTS, artifact_id())]
    assert registered['owner_id'] == UID


def test_audio_registration_without_a_job_refuses_a_foreign_owner(retry_sleeps, monkeypatch):
    rows = {
        ('users', 'synthetic-stranger'): {'data_protection_level': 'enhanced'},
        ('users', 'synthetic-stranger', 'conversations', CID): {'id': CID},
    }
    store = make_store(rows)
    with pytest.raises(ValueError, match='result requires an existing owner job'):
        register_batch_artifact(store, 'synthetic-stranger', SEG, RESULT_URI, 'audio', 0, item=result_item())


def test_shadow_cleanup_after_is_stamped_one_hour_out(monkeypatch):
    store = make_store(shadow_rows())
    before = time.time()
    register_shadow(store)
    stamped = store.client.rows[(ARTIFACTS, artifact_id(SHADOW_URI))]['cleanup_after'].timestamp()
    assert before + 3600 - 5 <= stamped <= time.time() + 3600 + 5


WINDOWS = ('recovery', 'disposition', 'terminal', 'provider', 'redrive', 'redrive_language')


def test_recovery_payload_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_empty_disposition_registration_replays_read_abort(retry_sleeps, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    store = window_store('disposition')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_empty_disposition_gate_is_env_gated(monkeypatch):
    store = window_store('disposition')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_terminal_empty_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = window_store('terminal')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_provider_intent_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = window_store('provider')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_speech_redrive_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = window_store('redrive')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_redrive_language_handoff_registration_replays_read_abort(retry_sleeps, monkeypatch):
    store = window_store('redrive_language')
    script_reads(store.client, monkeypatch, abort={1})
    assert register_window(store) == artifact_id()


def test_recovery_token_rotation_between_attempts_refuses(retry_sleeps, monkeypatch):
    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=lambda attempt: rotate_window_token(store, attempt))
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_empty_disposition_window_rotation_between_attempts_refuses(retry_sleeps, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    store = window_store('disposition')
    script_reads(store.client, monkeypatch, abort={1}, mutate=lambda attempt: rotate_window_token(store, attempt))
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_terminal_empty_window_rotation_between_attempts_refuses(retry_sleeps, monkeypatch):
    store = window_store('terminal')
    script_reads(store.client, monkeypatch, abort={1}, mutate=lambda attempt: rotate_window_token(store, attempt))
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_provider_window_reset_between_attempts_refuses(retry_sleeps, monkeypatch):
    def reset_intent(attempt):
        store.client.rows[(JOBS, SEG)]['provider_intent'] = {}

    store = window_store('provider')
    script_reads(store.client, monkeypatch, abort={1}, mutate=reset_intent)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_speech_redrive_window_reset_between_attempts_refuses(retry_sleeps, monkeypatch):
    def reset_redrive(attempt):
        store.client.rows[(JOBS, SEG)]['speech_redrive'] = {}

    store = window_store('redrive')
    script_reads(store.client, monkeypatch, abort={1}, mutate=reset_redrive)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_redrive_language_handoff_reset_between_attempts_refuses(retry_sleeps, monkeypatch):
    def reset_redrive(attempt):
        store.client.rows[(JOBS, SEG)]['speech_redrive'] = {'paid_epoch': 3, 'provider': 'soniox'}

    store = window_store('redrive_language')
    script_reads(store.client, monkeypatch, abort={1}, mutate=reset_redrive)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_privacy_generation_change_between_attempts_refuses(retry_sleeps, monkeypatch):
    def bump_generation(attempt):
        store.client.rows[(PRIVACY, OWNER_KEY)] = {'generation': 1}

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=bump_generation)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'privacy_generation_changed'


def test_account_deletion_between_attempts_refuses(retry_sleeps, monkeypatch):
    def delete_account(attempt):
        store.client.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=delete_account)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'account_deleted'


def test_account_missing_between_attempts_refuses(retry_sleeps, monkeypatch):
    def drop_user(attempt):
        store.client.rows.pop(('users', UID), None)

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=drop_user)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'account_missing'


def test_data_protection_change_between_attempts_refuses(retry_sleeps, monkeypatch):
    def restrict_owner(attempt):
        store.client.rows[('users', UID)]['data_protection_level'] = 'restricted'

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=restrict_owner)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'data_protection_changed'


def test_conversation_deletion_between_attempts_refuses(retry_sleeps, monkeypatch):
    def delete_conversation(attempt):
        store.client.rows[('users', UID, 'deleted_conversations', CID)] = {'deleted': True}

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=delete_conversation)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'conversation_deleted'


def test_recording_privacy_change_between_attempts_refuses(retry_sleeps, monkeypatch):
    def flip_privacy(attempt):
        store.client.rows[('users', UID, 'conversations', CID)].update(
            {'record_lane_owner': 'batch_live_v1', 'uses_custom_stt': True}
        )

    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1}, mutate=flip_privacy)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store)
    assert raised.value.reason.value == 'recording_privacy_changed'


def test_lease_loss_between_attempts_refuses(retry_sleeps, monkeypatch):
    def revoke_lease(attempt):
        store.client.rows[(JOBS, SEG)]['state'] = 'queued'

    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1}, mutate=revoke_lease)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_result(store)
    assert raised.value.reason.value == 'result_lease_lost'


def test_voice_window_expiry_between_attempts_refuses(retry_sleeps, monkeypatch):
    from utils.batch_pipeline import retention as retention_module

    deadlines = iter([time.time() + 7200, time.time() + 60])
    monkeypatch.setattr(retention_module, 'voice_deadline', lambda capture_at, finalized_at=None: next(deadlines))
    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with pytest.raises(PermissionError, match='voice evidence upload cannot finish within retention window'):
        register_voice(store)


def test_voice_projection_missing_refuses_without_replay(retry_sleeps, monkeypatch):
    rows = voice_rows()
    rows[(RESULTS, SEG)] = {}
    store = make_store(rows)
    with pytest.raises(PermissionError, match='voice evidence requires current sync-off batch projection'):
        register_voice(store)
    assert len(store.client.transactions) == 1


def test_voice_sync_opt_out_binding_missing_refuses_without_replay(retry_sleeps, monkeypatch):
    rows = voice_rows()
    rows[(JOBS, SEG)]['projection_binding'] = {'owner_id': UID}
    store = make_store(rows)
    with pytest.raises(PermissionError, match='voice evidence requires current sync-off batch projection'):
        register_voice(store)
    assert len(store.client.transactions) == 1


def test_voice_window_requires_a_work_item(retry_sleeps, monkeypatch):
    store = make_store(voice_rows())
    with pytest.raises(PermissionError, match='voice evidence requires current sync-off batch projection'):
        register_batch_artifact(store, UID, SEG, VOICE_URI, 'voice_evidence', 0, item=None)


def test_voice_projection_rotation_between_attempts_refuses(retry_sleeps, monkeypatch):
    def clear_projection(attempt):
        store.client.rows[(RESULTS, SEG)]['projection_parts'] = {}

    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1}, mutate=clear_projection)
    with pytest.raises(PermissionError, match='voice evidence requires current sync-off batch projection'):
        register_voice(store)


def test_voice_sync_binding_flip_between_attempts_refuses(retry_sleeps, monkeypatch):
    def flip_binding(attempt):
        store.client.rows[(JOBS, SEG)]['projection_binding']['private_cloud_sync_enabled'] = True

    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1}, mutate=flip_binding)
    with pytest.raises(PermissionError, match='voice evidence requires current sync-off batch projection'):
        register_voice(store)


def test_voice_cleanup_after_clamps_to_the_result_expiry(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from utils.batch_pipeline import retention as retention_module

    capture = time.time() - 10
    rows = voice_rows()
    rows[(JOBS, SEG)]['capture_at'] = capture
    # Clamp target below the capture deadline: expires - 45d + 1h must win the min().
    expires = datetime.fromtimestamp(capture, timezone.utc) + timedelta(days=45, seconds=80000)
    rows[(RESULTS, SEG)]['expires_at'] = expires
    store = make_store(rows)
    register_voice(store, item=voice_item(capture))
    clamped = expires - retention_module.RECEIPT_RETENTION + timedelta(seconds=FINALIZED_TTL)
    assert store.client.rows[(ARTIFACTS, artifact_id(VOICE_URI))]['cleanup_after'] == clamped


def test_conversation_ids_compose_job_binding_and_item_targets(monkeypatch):
    rows = leased_rows()
    rows[(JOBS, SEG)]['projection_binding'] = {'target_conversation_id': 'synthetic-target-conversation'}
    rows[('users', UID, 'conversations', 'synthetic-target-conversation')] = {'id': 'synthetic-target-conversation'}
    item = replace(result_item(), conversation_id='synthetic-item-conversation')
    rows[('users', UID, 'conversations', 'synthetic-item-conversation')] = {'id': 'synthetic-item-conversation'}
    store = make_store(rows)
    register_result(store, item=item)
    assert store.client.rows[(ARTIFACTS, artifact_id())]['conversation_ids'] == [
        CID,
        'synthetic-target-conversation',
        'synthetic-item-conversation',
    ]


def test_artifact_document_fields_parity(monkeypatch):
    store = make_store(leased_rows())
    registered = register_result(store)
    row = store.client.rows[(ARTIFACTS, registered)]
    assert row['owner_key'] == OWNER_KEY
    assert row['owner_id'] == UID
    assert row['segment_id'] == SEG
    assert row['uri'] == RESULT_URI
    assert row['kind'] == 'result'
    assert row['privacy_generation'] == 0
    # The job and the item both name the same conversation; the stored list
    # keeps the raw composition and only the fence walk dedups.
    assert row['conversation_ids'] == [CID, CID]
    assert row['capture_at'] == 100.0
    assert row['duration_seconds'] == 10.0


def test_recovery_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]
    assert len(store.client.transactions) == 5


def test_empty_disposition_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    store = window_store('disposition')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_terminal_empty_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = window_store('terminal')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_provider_intent_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = window_store('provider')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_speech_redrive_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = window_store('redrive')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_redrive_language_handoff_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = window_store('redrive_language')
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_window(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_shadow_audio_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = make_store(shadow_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_shadow(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_voice_evidence_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_voice(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_audio_registration_budget_exhausts_atomically(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_audio(store)
    assert not [path for path in store.client.rows if path[0] == ARTIFACTS]


def test_recovery_payload_requires_the_quarantined_running_state(retry_sleeps, monkeypatch):
    rows = base_rows()
    job = window_job('recovery')
    job['recovery_state'] = 'held'
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_empty_disposition_requires_the_failed_held_state(retry_sleeps, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    rows = base_rows()
    job = window_job('disposition')
    job['recovery_state'] = 'held'
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_terminal_empty_requires_held_or_failed_held_recovery_state(retry_sleeps, monkeypatch):
    rows = base_rows()
    job = window_job('terminal')
    job['recovery_state'] = 'running'
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_leased_job_registers_without_a_provider_window(retry_sleeps, monkeypatch):
    """A live lease admits any token: the write windows only guard non-leased states."""
    rows = base_rows()
    job = window_job('provider')
    job['state'] = 'leased'
    rows[(JOBS, SEG)] = job
    store = make_store(rows)
    register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert store.client.rows[(ARTIFACTS, artifact_id(window_uri(token=OTHER_TOKEN)))]['kind'] == 'result'


def test_speech_redrive_requires_the_running_redrive_state(retry_sleeps, monkeypatch):
    rows = base_rows()
    job = window_job('redrive')
    job['speech_redrive']['state'] = 'held'
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_recovery_payload_refuses_a_foreign_uri_token(retry_sleeps, monkeypatch):
    store = window_store('recovery')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert raised.value.reason.value == 'result_lease_lost'


def test_empty_disposition_refuses_a_foreign_uri_token(retry_sleeps, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    store = window_store('disposition')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert raised.value.reason.value == 'result_lease_lost'


def test_terminal_empty_refuses_a_foreign_uri_token(retry_sleeps, monkeypatch):
    store = window_store('terminal')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert raised.value.reason.value == 'result_lease_lost'


def test_provider_intent_refuses_a_foreign_uri_token(retry_sleeps, monkeypatch):
    store = window_store('provider')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert raised.value.reason.value == 'result_lease_lost'


def test_speech_redrive_refuses_a_foreign_uri_token(retry_sleeps, monkeypatch):
    store = window_store('redrive')
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, uri=window_uri(token=OTHER_TOKEN))
    assert raised.value.reason.value == 'result_lease_lost'


def test_recovery_payload_requires_the_recorded_privacy_generation(retry_sleeps, monkeypatch):
    store = window_store('recovery')
    store.client.rows[(PRIVACY, OWNER_KEY)] = {'generation': 1}
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, generation=1)
    assert raised.value.reason.value == 'result_lease_lost'


def test_provider_intent_requires_the_recorded_privacy_generation(retry_sleeps, monkeypatch):
    store = window_store('provider')
    store.client.rows[(PRIVACY, OWNER_KEY)] = {'generation': 1}
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, generation=1)
    assert raised.value.reason.value == 'result_lease_lost'


def test_speech_redrive_requires_the_recorded_privacy_generation(retry_sleeps, monkeypatch):
    store = window_store('redrive')
    store.client.rows[(PRIVACY, OWNER_KEY)] = {'generation': 1}
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, generation=1)
    assert raised.value.reason.value == 'result_lease_lost'


def test_terminal_empty_requires_the_recorded_privacy_generation(retry_sleeps, monkeypatch):
    store = window_store('terminal')
    store.client.rows[(PRIVACY, OWNER_KEY)] = {'generation': 1}
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(store, generation=1)
    assert raised.value.reason.value == 'result_lease_lost'


def test_redrive_epoch_gate_requires_the_policy_flag(retry_sleeps, monkeypatch):
    rows = base_rows()
    job = window_job('redrive')
    job.pop('policy_parts')
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_redrive_language_handoff_requires_a_guarded_language(retry_sleeps, monkeypatch):
    rows = base_rows()
    job = window_job('redrive_language')
    job.pop('stt_route')
    rows[(JOBS, SEG)] = job
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_window(make_store(rows))
    assert raised.value.reason.value == 'result_lease_lost'


def test_second_voice_projection_part_extends_the_stamped_conversations(monkeypatch):
    rows = voice_rows()
    rows[(RESULTS, SEG)]['projection_parts']['1'] = {
        'conversation_id': 'synthetic-second-voice-part',
        'speaker_scope': 'final:batch:' + SEG + '-b',
    }
    rows[('users', UID, 'conversations', 'synthetic-second-voice-part')] = {'id': 'synthetic-second-voice-part'}
    store = make_store(rows)
    register_voice(store)
    stamped = store.client.rows[(ARTIFACTS, artifact_id(VOICE_URI))]['conversation_ids']
    assert 'synthetic-second-voice-part' in stamped


def test_voice_window_margin_requires_upload_headroom(retry_sleeps, monkeypatch):
    """A result expiry that pulls voice_due inside the upload window refuses registration."""
    from datetime import datetime, timedelta, timezone

    rows = voice_rows()
    # expires - RECEIPT_RETENTION + FINALIZED_TTL = now + 1200 < now + UPLOAD_PENDING_SECONDS.
    rows[(RESULTS, SEG)]['expires_at'] = datetime.now(timezone.utc) + timedelta(seconds=1200 + 45 * 86400 - 3600)
    store = make_store(rows)
    with pytest.raises(PermissionError, match='voice evidence upload cannot finish within retention window'):
        register_voice(store)
    assert len(store.client.transactions) == 1


def test_kill_switch_replays_nothing_for_recovery_payloads(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store = window_store('recovery')
    script_reads(store.client, monkeypatch, abort={1})
    with pytest.raises(Aborted):
        register_window(store)
    assert len(store.client.transactions) == 1


def test_kill_switch_replays_nothing_for_voice_evidence(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with pytest.raises(Aborted):
        register_voice(store)
    assert len(store.client.transactions) == 1


def test_expired_then_aborted_replays_across_both_budgets(retry_sleeps, instant_restarts, monkeypatch):
    store = make_store(leased_rows())
    errors = {
        1: InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
        2: Aborted(ABORT_MESSAGE),
    }
    original = StrictFirestoreDocument.get

    def get(self, transaction=None, **kwargs):
        if transaction is not None and len(store.client.transactions) in errors:
            raise errors[len(store.client.transactions)]
        return original(self, transaction=transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 3
    assert retry_sleeps == [pytest.approx(0.1)]


def test_expiry_ceiling_without_deadline_is_three_fresh_chains(retry_sleeps, instant_restarts, monkeypatch):
    store = make_store(leased_rows())
    script_reads(
        store.client,
        monkeypatch,
        abort={1, 2, 3, 4, 5, 6, 7, 8, 9},
        error=InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
    )
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert len(store.client.transactions) == 9


def test_recovery_payload_replays_an_expired_transaction(retry_sleeps, instant_restarts, monkeypatch):
    store = window_store('recovery')
    script_reads(
        store.client,
        monkeypatch,
        abort={1},
        error=InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
    )
    assert register_window(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_audio_registration_replays_an_expired_transaction(retry_sleeps, instant_restarts, monkeypatch):
    store = make_store(leased_rows())
    script_reads(
        store.client,
        monkeypatch,
        abort={1},
        error=InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
    )
    assert register_audio(store) == artifact_id()


def test_default_operation_name_is_unchanged_for_existing_callers(no_retry_sleep, caplog):
    from unittest.mock import Mock

    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('read-time contention'), True])
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert run_retention_transaction(client, operation) is True
    recovered = [record.getMessage() for record in caplog.records if 'outcome=recovered' in record.getMessage()]
    assert recovered and 'operation=batch_retention' in recovered[0]


def test_register_label_differs_from_the_completion_label(caplog):
    from unittest.mock import Mock

    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('read-time contention'), True])
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        run_retention_transaction(client, operation, operation_name='batch_artifact_register')
    recovered = [record.getMessage() for record in caplog.records if 'outcome=recovered' in record.getMessage()]
    assert recovered and 'operation=batch_artifact_register' in recovered[0]


def test_completion_expiry_still_uses_the_shared_helper(monkeypatch):
    from unittest.mock import Mock

    calls = []

    def run(client, operation, *, operation_name='batch_retention', storm_damper=None):
        calls.append(operation_name)

    monkeypatch.setattr(retention_module, 'run_retention_transaction', run)
    store = Mock(namespace=NS)
    expire_completed_segment(store, UID, SEG, 0.0)
    assert calls == ['batch_retention']


def test_register_under_deadline_scope_stops_before_the_budget(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with transaction_retry_deadline_scope(time.monotonic() + 10):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            register_result(store)
    assert raised.value.reason == 'deadline_exhausted'
    assert len(store.client.transactions) == 1


def test_first_attempt_is_never_deadline_gated(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    script_reads(store.client, monkeypatch, abort={1})
    with transaction_retry_deadline_scope(time.monotonic() - 1):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            register_result(store)
    assert raised.value.reason == 'deadline_exhausted'
    assert len(store.client.transactions) == 1
    assert retry_sleeps == []


@pytest.fixture
def no_retry_sleep(monkeypatch):
    actual = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast(*args, **kwargs):
        return actual(*args, **kwargs, sleep=lambda _: None)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast)


@pytest.fixture(autouse=True)
def _gpu_stage_env(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


class _Samples:
    def __init__(self, seconds):
        self.size = int(seconds * 16000)

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return _Samples((key.stop - key.start) / 16000)


class _Words:
    def transcribe_batch(self, samples):
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def _worker(persist, on_failure=None, io_concurrency=None):
    from diarizer.batch_pipeline import PipelineWorker

    settings = dict(
        language_of=lambda item: 'en',
        decode=lambda work: _Samples(work.duration_seconds),
        vad=lambda samples: [(0, len(samples) / 16000)],
        words_providers={'parakeet': _Words()},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=persist,
    )
    if on_failure is not None:
        settings['on_failure'] = on_failure
    if io_concurrency is not None:
        settings['io_concurrency'] = io_concurrency
    return PipelineWorker(**settings)


def _unit(key='a', duration=2):
    return WorkItem(key, 'owner-' + key, 100.0, 'encrypted://' + key, duration, Priority.FRESH)


def test_persist_contention_exhaustion_fails_only_its_own_unit():
    saved, failures = {}, []

    def persist(work, payload):
        if work.segment_id == 'a':
            raise FirestoreContentionExhausted('synthetic persist budget exhausted')
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    results = _worker(persist, lambda item, name: failures.append((item.segment_id, name))).process_batch(
        [_unit('a'), _unit('b')]
    )
    assert [result.segment_id for result in results] == ['b']
    assert set(saved) == {'b'}
    assert failures == [('a', 'FirestoreContentionExhausted')]


def test_persist_read_abort_does_not_poison_sibling_results():
    saved, failures = {}, []

    def persist(work, payload):
        if work.segment_id == 'a':
            raise Aborted('synthetic persist read abort')
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    results = _worker(persist, lambda item, name: failures.append((item.segment_id, name))).process_batch(
        [_unit('a'), _unit('b')]
    )
    assert [result.segment_id for result in results] == ['b']
    assert failures == [('a', 'Aborted')]


def test_fatal_cuda_error_still_wins_over_persist_failure():
    from utils.batch_pipeline.errors import FatalGpuError

    def persist(work, payload):
        raise RuntimeError('cuda error: out of memory at persist')

    with pytest.raises(FatalGpuError):
        _worker(persist).process_batch([_unit('a')])


def test_persist_registration_timeout_fails_its_own_unit():
    saved, failures = {}, []

    def persist(work, payload):
        if work.segment_id == 'a':
            raise TimeoutError('artifact registration too old to begin upload')
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    results = _worker(persist, lambda item, name: failures.append((item.segment_id, name))).process_batch(
        [_unit('a'), _unit('b')]
    )
    assert [result.segment_id for result in results] == ['b']
    assert failures == [('a', 'TimeoutError')]


def test_silence_unit_with_failing_persist_is_not_reported_success():
    from diarizer.batch_pipeline import PipelineWorker

    failures = []

    def persist(work, payload):
        raise FirestoreContentionExhausted('synthetic persist budget exhausted')

    worker = PipelineWorker(
        language_of=lambda item: 'en',
        decode=lambda work: _Samples(work.duration_seconds),
        vad=lambda samples: [],
        words_providers={'parakeet': _Words()},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=persist,
        on_failure=lambda item, name: failures.append((item.segment_id, name)),
    )
    results = worker.process_batch([_unit('a')])
    assert results == []
    assert failures == [('a', 'FirestoreContentionExhausted')]


def test_failed_persist_leaves_no_result_uri():
    def persist(work, payload):
        if work.segment_id == 'a':
            raise FirestoreContentionExhausted('synthetic persist budget exhausted')
        return 'encrypted-result://' + work.segment_id

    results = _worker(persist).process_batch([_unit('a'), _unit('b')])
    assert all(result.segment_id != 'a' for result in results)
    assert all(result.result_uri.startswith('encrypted-result://') for result in results)


def test_every_persist_failure_is_recorded_per_unit():
    failures = []

    def persist(work, payload):
        raise FirestoreContentionExhausted('synthetic persist budget exhausted')

    results = _worker(persist, lambda item, name: failures.append((item.segment_id, name))).process_batch(
        [_unit('a'), _unit('b')]
    )
    assert results == []
    assert failures == [('a', 'FirestoreContentionExhausted'), ('b', 'FirestoreContentionExhausted')]


def test_concurrent_persist_failure_is_isolated_per_unit():
    saved, failures = {}, []

    def persist(work, payload):
        if work.segment_id == 'a':
            raise FirestoreContentionExhausted('synthetic persist budget exhausted')
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    worker = _worker(persist, lambda item, name: failures.append((item.segment_id, name)), io_concurrency=2)
    results = worker.process_batch([_unit('a'), _unit('b')])
    assert [result.segment_id for result in results] == ['b']
    assert set(saved) == {'b'}
    assert failures == [('a', 'FirestoreContentionExhausted')]


def test_audio_registration_replays_commit_abort(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    abort_commits(store.client, monkeypatch, attempts={1})
    assert register_audio(store) == artifact_id()
    assert len(store.client.transactions) == 2


def test_voice_evidence_registration_replays_commit_abort(retry_sleeps, monkeypatch):
    store = make_store(voice_rows())
    abort_commits(store.client, monkeypatch, attempts={1})
    assert register_voice(store) == artifact_id(VOICE_URI)


def test_commit_abort_budget_exhausts_after_five_bodies(retry_sleeps, monkeypatch):
    store = make_store(leased_rows())
    abort_commits(store.client, monkeypatch, attempts={1, 2, 3, 4, 5})
    with pytest.raises(FirestoreContentionExhausted):
        register_result(store)
    assert len(store.client.transactions) == 5


def test_mid_retry_shadow_state_demotion_refuses(retry_sleeps, monkeypatch):
    def demote_shadow(attempt):
        store.client.rows[(SHADOW_JOBS, SEG)]['state'] = 'projected'

    store = make_store(shadow_rows())
    script_reads(store.client, monkeypatch, abort={1}, mutate=demote_shadow)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        register_shadow(store)
    assert raised.value.args[0] == 'shadow_artifact_state'


def test_mid_retry_voice_expiry_pulls_the_window_inside_the_margin(retry_sleeps, monkeypatch):
    from datetime import datetime, timedelta, timezone

    def clamp_expiry(attempt):
        rows = store.client.rows[(RESULTS, SEG)]
        rows['expires_at'] = datetime.now(timezone.utc) + timedelta(seconds=1200 + 45 * 86400 - 3600)

    store = make_store(voice_rows())
    script_reads(store.client, monkeypatch, abort={1}, mutate=clamp_expiry)
    with pytest.raises(PermissionError, match='voice evidence upload cannot finish within retention window'):
        register_voice(store)


def test_kill_switch_still_registers_successful_artifacts(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store = make_store(leased_rows())
    assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 1
    assert store.client.rows[(ARTIFACTS, artifact_id())]['uri'] == RESULT_URI


def test_expiry_restart_does_not_pollute_contention_logs(retry_sleeps, instant_restarts, monkeypatch, caplog):
    store = make_store(leased_rows())
    script_reads(
        store.client,
        monkeypatch,
        abort={1},
        error=InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
    )
    with caplog.at_level(logging.DEBUG, logger='database.firestore_transaction_retry'):
        assert register_result(store) == artifact_id()
    assert len(store.client.transactions) == 2
    assert not [record for record in caplog.records if 'firestore_transaction_contention' in record.getMessage()]
