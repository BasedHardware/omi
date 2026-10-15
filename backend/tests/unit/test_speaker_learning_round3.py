"""Round-3 aborted-bookkeeping fallback contracts.

A confirmed abort involving optional ledger staging reruns the whole
assignment once, label-only, in a fresh transaction that rereads authority
and recomputes evidence/retraction. Ambiguous commit failures propagate;
staging failures degrade bookkeeping without touching the label. Synthetic
strict storage and offline SDK references with mocked RPCs only.
"""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument, ServiceUnavailable
from google.cloud.firestore_v1._helpers import decode_dict
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.types import CommitResponse

from database import conversations as db
from database import speaker_assignment_effects as effects
from database import speaker_learning_jobs as ledger
from utils import speaker_learning_jobs as jobs
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
    StrictFirestoreTransaction,
)
from tests.unit.test_speaker_learning_durable_jobs import (
    world,
    assign,
    UID,
    CONV,
    CONV_PATH,
    LEDGER_PATH,
    PERSON_PATH,
)

USER_PATH = ('users', UID)


def decoded(world):
    raw = deepcopy(world.store.rows[CONV_PATH])
    raw['transcript_segments'] = db.decode_transcript_segments_verified(
        UID, raw['transcript_segments'], raw.get('transcript_segments_compressed', False)
    )
    raw['manual_speaker_assignments'] = db.decode_manual_speaker_assignments(
        UID, raw.get('manual_speaker_assignments'), raw.get('manual_speaker_assignments_compressed', False)
    )
    return raw


def atomic_hooks(world, monkeypatch, mutate=None):
    begin = StrictFirestoreTransaction._begin
    commit = StrictFirestoreTransaction._commit

    def atomic_begin(tx, retry_id=None):
        tx.review_before = deepcopy(tx._database.rows)
        return begin(tx, retry_id)

    def rollback(tx):
        tx._database.rows.clear()
        tx._database.rows.update(deepcopy(tx.review_before))
        if mutate is not None:
            mutate(tx._database.rows)

    def commit_failure(tx):
        if any(path == LEDGER_PATH for path, _ in tx.sets):
            raise Aborted('injected ledger-only contention')
        return commit(tx)

    monkeypatch.setattr(StrictFirestoreTransaction, '_begin', atomic_begin)
    monkeypatch.setattr(StrictFirestoreTransaction, '_rollback', rollback)
    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_failure)


def counted_gets(world, monkeypatch):
    original = StrictFirestoreDocument.get
    gets = []

    def counted(ref, *args, **kwargs):
        tx = kwargs.get('transaction') or (args[0] if args else None)
        gets.append((tx, ref.path))
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    return gets


def sdk_harness(world, monkeypatch, commit_impl, get_impl=None):
    api = MagicMock()
    counter = [0]

    def begin(request, **kwargs):
        counter[0] += 1
        return SimpleNamespace(transaction=f'local-review-transaction-{counter[0]}'.encode())

    api.begin_transaction.side_effect = begin
    client = OfflineFirestoreClient(project='local-review', api=api)
    ledger_name = client.document('/'.join(LEDGER_PATH))._document_path
    baseline = deepcopy(world.store.rows)
    submitted = []
    seen = []

    def default_get(ref, *args, **kwargs):
        tx = kwargs.get('transaction')
        if tx is not None:
            assert not tx._write_pbs, 'transactional reads must precede staged writes'
            if all(tx is not other for other in seen):
                seen.append(tx)
        return StrictFirestoreSnapshot(world.store.rows.get(tuple(ref._path)))

    def default_commit(request, **kwargs):
        writes = list(request['writes'])
        submitted.append(writes)
        assert world.store.rows == baseline, 'no primary write may persist before the successful commit'
        for write in writes:
            path = tuple(write.update.name.split('/documents/', 1)[1].split('/'))
            world.store.rows.setdefault(path, {}).update(decode_dict(write.update.fields, client))
        return CommitResponse(commit_time=world.clock[0])

    monkeypatch.setattr(DocumentReference, 'get', get_impl or default_get)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: client)
    api.commit.side_effect = commit_impl or default_commit
    return SimpleNamespace(
        api=api,
        client=client,
        ledger_name=ledger_name,
        baseline=baseline,
        submitted=submitted,
        seen=seen,
    )


def aborting_commit(harness):
    def commit(request, **kwargs):
        harness.submitted.append(list(request['writes']))
        raise Aborted('synthetic contention')

    return commit


@pytest.mark.parametrize('failure', ['stage', 'commit'])
def test_ledger_bookkeeping_boundary_falls_back_label_only(world, monkeypatch, failure):
    baseline = deepcopy(world.store.rows)
    begin = StrictFirestoreTransaction._begin
    stage = StrictFirestoreTransaction.set
    commit = StrictFirestoreTransaction._commit
    prepare = ledger.prepare_assignment_jobs
    prepared = []
    fallback = MagicMock()

    def atomic_begin(tx, retry_id=None):
        tx.review_before = deepcopy(tx._database.rows)
        return begin(tx, retry_id)

    def rollback(tx):
        tx._database.rows.clear()
        tx._database.rows.update(deepcopy(tx.review_before))

    def stage_failure(tx, ref, payload):
        if ref.path == LEDGER_PATH and failure == 'stage':
            raise ValueError('injected ledger-only staging failure')
        return stage(tx, ref, payload)

    def commit_failure(tx):
        if any(path == LEDGER_PATH for path, _ in tx.sets) and failure == 'commit':
            raise Aborted('injected ledger-only contention')
        return commit(tx)

    def counted_prepare(*args, **kwargs):
        prepared.append(True)
        return prepare(*args, **kwargs)

    monkeypatch.setattr(StrictFirestoreTransaction, '_begin', atomic_begin)
    monkeypatch.setattr(StrictFirestoreTransaction, '_rollback', rollback)
    monkeypatch.setattr(StrictFirestoreTransaction, 'set', stage_failure)
    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_failure)
    monkeypatch.setattr(ledger, 'prepare_assignment_jobs', counted_prepare)
    monkeypatch.setattr(effects, 'record_fallback', fallback)

    result = assign(person_id='p', segment_ids=['s0'])

    assert decoded(world)['transcript_segments'][0]['person_id'] == 'p'
    assert world.store.rows[PERSON_PATH]['label_evidence']['manual_labels'] == 1
    assert 'voice_learning_job' not in world.store.rows[PERSON_PATH]
    assert LEDGER_PATH not in world.store.rows
    assert result[0]['_speaker_learning_queued'] is False
    assert world.events == []
    assert len(prepared) == 1
    assert fallback.call_count == 1
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    if failure == 'stage':
        assert len(world.store.transactions) == 1
    else:
        assert len(world.store.transactions) == 2
        assert world.store.transactions[0].sets and world.store.transactions[-1].sets == []
        assert world.store.rows != baseline


def test_sdk_five_ledger_aborts_fall_back_to_fresh_label_only(world, monkeypatch):
    harness = sdk_harness(world, monkeypatch, None)
    baseline = harness.baseline

    def commit(request, **kwargs):
        writes = list(request['writes'])
        harness.submitted.append(writes)
        assert world.store.rows == baseline, 'no primary write may persist before the successful commit'
        if any(write.update.name == harness.ledger_name for write in writes):
            raise Aborted('synthetic contention on the optional learning ledger')
        for write in writes:
            path = tuple(write.update.name.split('/documents/', 1)[1].split('/'))
            world.store.rows.setdefault(path, {}).update(decode_dict(write.update.fields, harness.client))
        return CommitResponse(commit_time=world.clock[0])

    harness.api.commit.side_effect = commit

    result = assign(person_id='p', segment_ids=['s0'])

    assert len(harness.submitted) == 6
    assert harness.api.rollback.call_count == 1
    ledgered = [any(w.update.name == harness.ledger_name for w in writes) for writes in harness.submitted]
    assert ledgered == [True] * 5 + [False]
    assert len(harness.seen) == 2, 'the label-only fallback must run in a fresh transaction'
    last_options = harness.api.begin_transaction.call_args_list[-1].kwargs['request']['options']
    assert last_options is None or not last_options.read_write.retry_transaction
    assert decoded(world)['transcript_segments'][0]['person_id'] == 'p'
    person = world.store.rows[PERSON_PATH]
    assert person['label_evidence']['manual_labels'] == 1
    assert 'voice_learning_job' not in person
    assert LEDGER_PATH not in world.store.rows
    assert result[0]['_speaker_learning_queued'] is False
    assert world.events == []


def test_fallback_recomputes_receipt_evidence_and_owner_retraction(world, monkeypatch):
    assign(is_user=True, segment_ids=['s0'])
    ledger_after_setup = deepcopy(world.store.rows[LEDGER_PATH])
    events_after_setup = list(world.events)

    def external_changes(rows):
        stored = deepcopy(rows[CONV_PATH])
        segments = db.decode_transcript_segments_verified(
            UID, stored['transcript_segments'], stored.get('transcript_segments_compressed', False)
        )
        receipt = db.decode_manual_speaker_assignments(
            UID,
            stored.get('manual_speaker_assignments'),
            stored.get('manual_speaker_assignments_compressed', False),
        )
        receipt['generation'] = 10
        receipt.setdefault('segments', {})['s1'] = {
            'generation': 10,
            'person_id': 'q',
            'is_user': False,
            'speaker_id': 0,
        }
        rows[CONV_PATH].update(
            db._prepare_conversation_for_write(
                {'transcript_segments': segments, 'manual_speaker_assignments': receipt}, UID, 'standard'
            )
        )
        person = rows[PERSON_PATH]
        evidence = dict(person.get('label_evidence') or {})
        evidence['manual_labels'] = 7
        evidence['counted'] = ['manual_labels:other']
        person['label_evidence'] = evidence
        rows[USER_PATH].update(
            speaker_embedding_base=[1.0, 0.0],
            owner_voice_confirmations=[
                {'conversation_id': CONV, 'segment_ids': ['s0'], 'embedding': [1.0, 0.0]},
                {'conversation_id': 'other', 'segment_ids': ['z'], 'embedding': [0.0, 1.0]},
            ],
        )

    atomic_hooks(world, monkeypatch, mutate=external_changes)
    gets = counted_gets(world, monkeypatch)

    result = assign(person_id='p', segment_ids=['s0'])

    assert len(world.store.transactions) == 3
    fallback_tx = world.store.transactions[-1]
    assert fallback_tx.sets == []
    updated = {path for path, _ in fallback_tx.updates}
    assert {CONV_PATH, PERSON_PATH, USER_PATH} <= updated
    fallback_reads = {path for tx, path in gets if tx is fallback_tx}
    assert {CONV_PATH, PERSON_PATH, USER_PATH} <= fallback_reads
    assert LEDGER_PATH not in fallback_reads

    conversation = decoded(world)
    receipt = conversation['manual_speaker_assignments']
    assert receipt['generation'] == 11
    assert receipt['segments']['s1']['generation'] == 10
    by_id = {s['id']: s for s in conversation['transcript_segments']}
    assert by_id['s0']['person_id'] == 'p'
    assert by_id['s1']['person_id'] == 'q'
    person = world.store.rows[PERSON_PATH]
    assert person['label_evidence']['manual_labels'] == 8
    assert 'manual_labels:other' in person['label_evidence']['counted']
    assert 'voice_learning_job' not in person
    user = world.store.rows[USER_PATH]
    assert user['owner_voice_confirmations'] == [
        {'conversation_id': 'other', 'segment_ids': ['z'], 'embedding': [0.0, 1.0]}
    ]
    assert user['speaker_embedding_base'] == [1.0, 0.0]
    assert world.store.rows[LEDGER_PATH] == ledger_after_setup
    assert world.events == events_after_setup
    assert result[0]['_speaker_learning_queued'] is False


def _lock(rows):
    rows[CONV_PATH]['is_locked'] = True


def _delete(rows):
    rows[CONV_PATH]['deleted'] = True


def _drop_person(rows):
    rows.pop(PERSON_PATH, None)


@pytest.mark.parametrize(
    'mutate,error',
    [
        pytest.param(_lock, PermissionError, id='locked'),
        pytest.param(_delete, LookupError, id='deleted'),
        pytest.param(_drop_person, LookupError, id='person_missing'),
    ],
)
def test_fallback_revalidates_authority_after_rollback(world, monkeypatch, mutate, error):
    atomic_hooks(world, monkeypatch, mutate=mutate)
    gets = counted_gets(world, monkeypatch)

    with pytest.raises(error):
        assign(person_id='p', segment_ids=['s0'])

    assert len(world.store.transactions) == 2
    fallback_tx = world.store.transactions[-1]
    assert fallback_tx.sets == [] and fallback_tx.updates == [] and fallback_tx.creates == []
    assert all(path != LEDGER_PATH for tx, path in gets if tx is fallback_tx)
    assert not any(s.get('person_id') == 'p' for s in decoded(world)['transcript_segments'])


@pytest.mark.parametrize(
    'injected',
    [
        pytest.param(DeadlineExceeded('commit deadline'), id='deadline'),
        pytest.param(ServiceUnavailable('commit unavailable'), id='unavailable'),
        pytest.param(ValueError('commit unavailable'), id='plain_valueerror'),
        pytest.param(InvalidArgument('invalid primary write'), id='invalid_argument'),
    ],
)
def test_ambiguous_commit_failures_propagate_without_fallback(world, monkeypatch, injected):
    def commit(request, **kwargs):
        harness.submitted.append(list(request['writes']))
        raise injected

    harness = sdk_harness(world, monkeypatch, commit)

    with pytest.raises(type(injected)) as raised:
        assign(person_id='p', segment_ids=['s0'])

    assert raised.value is injected
    assert len(harness.submitted) == 1
    assert harness.api.rollback.call_count == 1
    assert harness.api.begin_transaction.call_count == 1
    assert len(harness.seen) == 1
    assert world.store.rows == harness.baseline


def test_rollback_failure_replacing_commit_error_is_not_retried(world, monkeypatch):
    injected = DeadlineExceeded('commit deadline')

    def commit(request, **kwargs):
        harness.submitted.append(list(request['writes']))
        raise injected

    harness = sdk_harness(world, monkeypatch, commit)
    harness.api.rollback.side_effect = Aborted('rollback failed')

    with pytest.raises(Aborted) as raised:
        assign(person_id='p', segment_ids=['s0'])

    assert isinstance(raised.value.__context__, DeadlineExceeded)
    assert len(harness.submitted) == 1
    assert harness.api.begin_transaction.call_count == 1
    assert world.store.rows == harness.baseline


def test_label_only_fallback_is_bounded(world, monkeypatch):
    harness = sdk_harness(world, monkeypatch, None)
    harness.api.commit.side_effect = aborting_commit(harness)

    with pytest.raises(ValueError) as raised:
        assign(person_id='p', segment_ids=['s0'])

    assert isinstance(raised.value.__cause__, Aborted)
    assert len(harness.submitted) == 10
    ledgered = [any(w.update.name == harness.ledger_name for w in writes) for writes in harness.submitted]
    assert ledgered == [True] * 5 + [False] * 5
    assert len(harness.seen) == 2
    assert world.store.rows == harness.baseline


def test_primary_read_abort_without_bookkeeping_never_falls_back(world, monkeypatch):
    def get(ref, *args, **kwargs):
        raise Aborted('read contention')

    harness = sdk_harness(world, monkeypatch, None, get_impl=get)
    harness.api.commit.side_effect = aborting_commit(harness)

    with pytest.raises(Aborted):
        assign(person_id='p', segment_ids=['s0'])

    assert harness.api.begin_transaction.call_count == 1
    assert harness.api.commit.call_count == 0
    assert harness.api.rollback.call_count == 1
    assert world.store.rows == harness.baseline


def test_sdk_happy_path_commits_label_person_and_ledger_atomically(world, monkeypatch):
    harness = sdk_harness(world, monkeypatch, None)

    result = assign(person_id='p', segment_ids=['s0'])

    assert len(harness.submitted) == 1
    names = {w.update.name for w in harness.submitted[0]}
    assert harness.ledger_name in names
    assert len(harness.seen) == 1
    assert decoded(world)['transcript_segments'][0]['person_id'] == 'p'
    person = world.store.rows[PERSON_PATH]
    assert person['label_evidence']['manual_labels'] == 1
    assert person['voice_learning_job']['conversation_id'] == CONV
    assert LEDGER_PATH in world.store.rows
    assert result[0]['_speaker_learning_queued'] is True
    assert world.events == [('person', 'queued')]


def test_degraded_label_still_runs_immediate_teaching(world, monkeypatch):
    atomic_hooks(world, monkeypatch)
    result = assign(person_id='p', segment_ids=['s0'])
    assert result[0]['_speaker_learning_queued'] is False
    assert LEDGER_PATH not in world.store.rows
    assert 'voice_learning_job' not in world.store.rows[PERSON_PATH]
    assert len(world.store.transactions) == 2
    monkeypatch.setattr(ledger, 'ensure_job', MagicMock(side_effect=RuntimeError('ledger unavailable')))

    outcome = asyncio.run(jobs.run_authorized_person_learning(UID, 'p', CONV, ['s0']))

    assert outcome == 'no_audio'
    assert world.extract.await_count == 1
    assert world.extract.await_args.args == (UID, 'p', CONV, ['s0'])
