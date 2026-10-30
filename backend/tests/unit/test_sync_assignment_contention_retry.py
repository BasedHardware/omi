"""Exercise sync's real SDK decorator at the read-versus-commit retry boundary.

The SDK-surface fakes stage writes until commit; StrictFirestore intentionally
cannot model aborts or SDK retry. Shared-document contention is qualified in dev.
"""

from copy import deepcopy
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, ServiceUnavailable

import database.firestore_transaction_retry as firestore_transaction_retry
from database import conversations as conversations_db
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
    transaction_retry_deadline_scope,
)
from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD as MARKER
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_FIELD as FIELD
from utils.sync import assignment

EXTRACTIONS = {'version': 1, 'delegated_by_user': [], 'commitments_by_others': [], 'observed_issue_or_blocker': None}

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


def expired() -> InvalidArgument:
    return InvalidArgument(EXPIRED)


class FakeClock:
    """Monotonic clock shared by the retry gates, the reads, and the sleeps."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def sdk_assignment(monkeypatch):
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *args: None)
    # The retry runner now lives in database.sync_assignment.run_sync_assignment,
    # which resolves run_with_transaction_contention_retry from its source module
    # at call time; patch that module so the seam keeps controlling production.
    monkeypatch.setattr(
        firestore_transaction_retry,
        'run_with_transaction_contention_retry',
        partial(run_with_transaction_contention_retry, sleep=lambda _: None, random_value=lambda: 0),
    )
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)

    def build(*, read_errors=(), commit_errors=(), read_advance=None):
        store = _FakeFirestoreClient(None, list(commit_errors))
        errors = list(read_errors)
        read_transactions = []
        original_get = store.doc_ref.get

        def read(transaction=None):
            if transaction is None:
                return original_get(transaction=transaction)
            read_transactions.append(transaction)
            if read_advance is not None:
                read_advance()
            if errors:
                error = errors.pop(0)
                if error is not None:
                    raise error
            return original_get(transaction=transaction)

        monkeypatch.setattr(store.doc_ref, 'get', read)

        def body(transaction, user_ref, incoming, **kwargs):
            # Raise from a real decorated transaction's body, before any write.
            store.doc_ref.get(transaction=transaction)
            transaction.set(store.doc_ref, incoming)
            return incoming, True, incoming['transcript_segments']

        monkeypatch.setattr(assignment, 'assign_in_transaction', body)
        return store, read_transactions

    return build


def persist(store):
    return conversations_db.assign_sync_conversation('synthetic-unit', chunk('canonical', 1000), firestore_client=store)


@pytest.mark.parametrize('flag', [None, 'false'])
def test_default_off_retains_read_abort_without_replay(sdk_assignment, monkeypatch, flag):
    if flag is not None:
        monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', flag)
    store, reads = sdk_assignment(read_errors=[Aborted('contention')])
    with pytest.raises(Aborted):
        persist(store)
    assert len(store.transactions) == len(reads) == 1
    assert store.commits == []


def test_enabled_read_abort_uses_fresh_transaction_and_commits_once(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[Aborted('contention')])
    result, created, _ = persist(store)
    assert created and result['id'] == 'canonical'
    assert len(store.transactions) == 2
    assert reads == store.transactions
    assert store.transactions[0].rolled_back
    assert len(store.commits) == 1
    assert len(store.commits[0]['transcript_segments']) == 1


def test_enabled_read_abort_has_finite_outer_budget(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[Aborted('contention') for _ in range(5)])
    with pytest.raises(FirestoreContentionExhausted):
        persist(store)
    assert len(store.transactions) == len(reads) == 5
    assert store.commits == []


def test_commit_abort_keeps_sdk_retry_and_single_durable_write(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(commit_errors=[Aborted('commit contention')])
    persist(store)
    assert len(store.transactions) == 1
    assert len(reads) == 2
    assert len(store.commits) == 1


def test_sdk_exhaustion_cause_is_bounded_by_outer_budget(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(commit_errors=[Aborted('commit contention') for _ in range(25)])
    with pytest.raises(FirestoreContentionExhausted):
        persist(store)
    assert len(store.transactions) == 5
    assert len(reads) == 25
    assert store.commits == []


def test_expiry_restarts_still_work_inside_outer_contention_retry(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(
        read_errors=[None, Aborted('contention')],
        commit_errors=[InvalidArgument('The referenced transaction has expired or is no longer valid.')],
    )
    persist(store)
    assert len(store.transactions) == 3
    assert reads == store.transactions
    assert len(store.commits) == 1


def test_nested_expiry_keeps_one_chain_per_attempt_and_todays_three_chain_ceiling(sdk_assignment, monkeypatch):
    # The outer budget owns every attempt: an expired chain costs one outer
    # retry (no inner restarts, which once multiplied the worst case to 15
    # chains), and with no deadline in scope the storm keeps today's ceiling
    # of three fresh chains — run_transactional's default — rather than the
    # five-chain Aborted policy.
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(commit_errors=[expired() for _ in range(8)])
    with pytest.raises(FirestoreContentionExhausted) as raised:
        persist(store)
    assert raised.value.reason == 'attempts_exhausted'
    assert len(store.transactions) == len(reads) == 3
    assert store.commits == []


def test_nested_repeated_expiry_stops_before_the_deadline(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    clock = FakeClock()
    monkeypatch.setattr(
        firestore_transaction_retry,
        'run_with_transaction_contention_retry',
        partial(
            run_with_transaction_contention_retry,
            sleep=clock.sleep,
            random_value=lambda: 0,
            monotonic=clock.monotonic,
        ),
    )

    # Each transaction body's read charges 100 s of the 500 s budget; a retry
    # starts only while the remaining budget covers the last attempt's observed
    # duration x 1.5 (150 s, above the 30 s floor), so the fifth attempt's gate
    # stops the loop.
    def charge_read():
        clock.now += 100.0

    store, reads = sdk_assignment(commit_errors=[expired() for _ in range(8)], read_advance=charge_read)
    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 500.0):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            persist(store)

    assert raised.value.reason == 'deadline_exhausted'
    assert isinstance(raised.value.__cause__, InvalidArgument)
    assert len(store.transactions) == len(reads) == 4
    assert store.commits == []
    assert clock.monotonic() - start <= 500.0


def test_nested_expiry_recovers_within_budget_when_time_allows(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    clock = FakeClock()
    monkeypatch.setattr(
        firestore_transaction_retry,
        'run_with_transaction_contention_retry',
        partial(
            run_with_transaction_contention_retry,
            sleep=clock.sleep,
            random_value=lambda: 0,
            monotonic=clock.monotonic,
        ),
    )
    store, reads = sdk_assignment(commit_errors=[expired(), expired()])
    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 1260.0):
        result, created, _ = persist(store)

    assert created and result['id'] == 'canonical'
    assert len(store.transactions) == len(reads) == 3
    assert len(store.commits) == 1
    assert clock.monotonic() - start <= 1260.0


class _ReplaySnapshot:
    def __init__(self, data: Optional[Dict[str, Any]]):
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return deepcopy(self._data) if self._data is not None else None


class _ReplayDocumentReference:
    def __init__(self, client: '_ReplayFirestoreClient', path: Tuple[str, ...]):
        self._client = client
        self._path = path
        self.id = path[-1]

    def get(self, transaction: Optional['_ReplayTransaction'] = None) -> _ReplaySnapshot:
        if transaction is not None and transaction.staged:
            # Production rule: transaction reads come before the first write.
            raise RuntimeError('transaction read after a staged write')
        self._client.read_paths.append(self._path)
        return _ReplaySnapshot(self._client.rows.get(self._path))

    def collection(self, collection_id: str) -> '_ReplayCollectionReference':
        return _ReplayCollectionReference(self._client, (*self._path, collection_id))


class _ReplayCollectionReference:
    def __init__(self, client: '_ReplayFirestoreClient', path: Tuple[str, ...]):
        self._client = client
        self._path = path

    def document(self, document_id: str) -> _ReplayDocumentReference:
        return _ReplayDocumentReference(self._client, (*self._path, document_id))


class _ReplayTransaction:
    """The surface ``_Transactional.__call__`` drives, staging writes until commit.

    A failed commit stages nothing durable: ``_begin`` drops the failed attempt's
    staged writes, so an SDK same-chain replay re-runs the body against the same
    committed rows a fresh Firestore transaction would see.
    """

    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_ReplayFirestoreClient'):
        self._client = client
        self._id = f'txn-{len(client.transactions)}'.encode()
        self.staged: List[Tuple[str, Tuple[str, ...], Optional[Dict[str, Any]]]] = []
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id: Optional[bytes] = None) -> None:
        if retry_id is not None:
            self._id = retry_id
        self.staged = []

    def _rollback(self) -> None:
        self.rolled_back = True

    def set(self, doc_ref: _ReplayDocumentReference, payload: Dict[str, Any], merge: bool = False) -> None:
        self.staged.append(('set', doc_ref._path, payload))

    def update(self, doc_ref: _ReplayDocumentReference, payload: Dict[str, Any]) -> None:
        self.staged.append(('update', doc_ref._path, payload))

    def delete(self, doc_ref: _ReplayDocumentReference) -> None:
        self.staged.append(('delete', doc_ref._path, None))

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        applied = []
        for kind, path, payload in self.staged:
            applied.append((kind, path, payload))
            if kind == 'set':
                self._client.rows[path] = payload
            elif kind == 'update':
                self._client.rows.setdefault(path, {}).update(payload)
            else:
                self._client.rows.pop(path, None)
        self._client.commits.append(applied)


class _ReplayFirestoreClient:
    """Document rows plus SDK transactions that replay a chain in-process."""

    def __init__(self, commit_errors: List[BaseException] | None = None):
        self.rows: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        self.commit_errors = list(commit_errors or [])
        self.commits: List[List[Tuple[str, Tuple[str, ...], Optional[Dict[str, Any]]]]] = []
        self.transactions: List[_ReplayTransaction] = []
        self.read_paths: List[Tuple[str, ...]] = []

    def collection(self, collection_id: str) -> _ReplayCollectionReference:
        return _ReplayCollectionReference(self, (collection_id,))

    def transaction(self) -> _ReplayTransaction:
        transaction = _ReplayTransaction(self)
        self.transactions.append(transaction)
        return transaction


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_sdk_same_chain_replay_never_decodes_retained_extractions(monkeypatch, level):
    # Integrated #23738 regression: one Aborted commit makes the SDK replay the
    # whole production body on the same transaction id. Nothing may be stubbed:
    # the real assign_sync_conversation -> assign_in_transaction -> encode path
    # must carry the stored blob verbatim on both body executions.
    store = _ReplayFirestoreClient(commit_errors=[Aborted('commit contention')])
    stored = conversations_db.encode_conversation_for_write(
        'synthetic-unit',
        dict(
            chunk('existing', 1000),
            structured={'title': 'Synthetic'},
            data_protection_level=level,
            sync_content_revision=1,
            **{FIELD: EXTRACTIONS},
        ),
        level,
    )
    conversation_path = ('users', 'synthetic-unit', 'conversations', 'existing')
    store.rows[conversation_path] = deepcopy(stored)

    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', lambda *args: None)
    decode_calls = []
    real_decode = conversations_db.decode_open_loop_extractions

    def counting_decode(uid, raw, compressed):
        decode_calls.append(raw)
        return real_decode(uid, raw, compressed)

    monkeypatch.setattr(conversations_db, 'decode_open_loop_extractions', counting_decode)

    row, created, _ = conversations_db.assign_sync_conversation(
        'synthetic-unit',
        dict(chunk('append', 1060), data_protection_level=level),
        candidate_id='existing',
        firestore_client=store,
    )

    assert not created and row['id'] == 'existing'
    # One transaction chain: the SDK replayed the body after the aborted commit.
    [transaction] = store.transactions
    assert not transaction.rolled_back
    # Both body executions read the stored row without ever decoding it.
    assert store.read_paths.count(conversation_path) == 2
    assert decode_calls == []
    [commit] = store.commits
    written = next(payload for _, path, payload in commit if path == conversation_path and payload)
    assert written[FIELD] == stored[FIELD] and written[MARKER] == stored[MARKER]
    raw = store.rows[conversation_path]
    assert raw[FIELD] == stored[FIELD] and raw[MARKER] == stored[MARKER]
    assert real_decode('synthetic-unit', raw[FIELD], raw[MARKER]) == EXTRACTIONS


@pytest.mark.parametrize('error', [InvalidArgument('bad payload'), ServiceUnavailable('ambiguous transport failure')])
def test_non_contention_errors_are_not_replayed(sdk_assignment, monkeypatch, error):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[error])
    with pytest.raises(type(error)):
        persist(store)
    assert len(store.transactions) == len(reads) == 1
    assert store.commits == []


def test_batch_opt_in_retries_without_enabling_legacy_assignment(sdk_assignment):
    store, reads = sdk_assignment(read_errors=[Aborted('synthetic contention')])
    result, created, _ = conversations_db.assign_sync_conversation(
        'synthetic-unit', chunk('canonical', 1000), firestore_client=store, retry_contention=True
    )
    assert created and result['id'] == 'canonical'
    assert len(store.transactions) == len(reads) == 2
    assert len(store.commits) == 1


def timing_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('event=sync_assignment_timing ')]


def test_timing_counts_sdk_commit_retry_attempts_without_ids(sdk_assignment, monkeypatch, caplog):
    store, reads = sdk_assignment(commit_errors=[Aborted('commit contention')])
    fences = []
    with caplog.at_level('INFO', logger=conversations_db.logger.name):
        conversations_db.assign_sync_conversation(
            'synthetic-unit',
            chunk('canonical', 1000),
            firestore_client=store,
            retry_contention=True,
            before_assign=fences.append,
            timing=True,
        )
    assert len(store.commits) == 1 and len(fences) == len(reads) == 2
    [line] = timing_lines(caplog)
    fields = dict(token.split('=', 1) for token in line.split())
    assert fields['outcome'] == 'completed' and fields['attempts'] == '2'
    assert set(fields) == {
        'event',
        'outcome',
        'attempts',
        'live_overlap_ms',
        'fence_ms',
        'plan_ms',
        'encode_ms',
        'persist_ms',
        'body_ms',
        'commit_ms',
        'retry_ms',
        'index_ms',
        'donors',
        'total_ms',
    }
    assert all(value.isdigit() for key, value in fields.items() if key.endswith('_ms') or key == 'donors')
    assert 'synthetic-unit' not in line and 'canonical' not in line


def test_timing_reports_bounded_error_and_off_is_silent(sdk_assignment, caplog):
    store, _ = sdk_assignment(read_errors=[InvalidArgument('bad payload')])
    with caplog.at_level('INFO', logger=conversations_db.logger.name):
        with pytest.raises(InvalidArgument):
            conversations_db.assign_sync_conversation(
                'synthetic-unit', chunk('canonical', 1000), firestore_client=store, timing=True
            )
    [line] = timing_lines(caplog)
    assert ' outcome=error ' in line and line.endswith(' exception_type=InvalidArgument')
    assert 'bad payload' not in line
    caplog.clear()
    store, _ = sdk_assignment()
    with caplog.at_level('INFO', logger=conversations_db.logger.name):
        persist(store)
    assert timing_lines(caplog) == []


def test_timing_plan_excludes_nested_encode_and_counts_donors(sdk_assignment, monkeypatch, caplog):
    import time as real_time

    store, _ = sdk_assignment()

    def body(transaction, user_ref, incoming, **kwargs):
        real_time.sleep(0.01)
        kwargs['encode']({'id': 'canonical'})
        merged = {**incoming, 'sync_merged_from': ['d1', 'd2']}
        transaction.set(store.doc_ref, merged)
        return merged, True, merged['transcript_segments']

    monkeypatch.setattr(assignment, 'assign_in_transaction', body)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(conversations_db, 'encode_sync_assignment_plan', lambda *args: real_time.sleep(0.05) or {})
    with caplog.at_level('INFO', logger=conversations_db.logger.name):
        conversations_db.assign_sync_conversation(
            'synthetic-unit', chunk('canonical', 1000), firestore_client=store, timing=True
        )
    [line] = timing_lines(caplog)
    fields = dict(token.split('=', 1) for token in line.split())
    assert int(fields['encode_ms']) >= 50
    assert int(fields['plan_ms']) < int(fields['encode_ms'])
    assert fields['donors'] == '2'


def test_timing_logs_live_overlap_lookup_failure(sdk_assignment, monkeypatch, caplog):
    store, _ = sdk_assignment()
    monkeypatch.setattr(conversations_db, 'live_overlap_enabled', lambda: True)

    def broken(*args):
        raise RuntimeError('synthetic overlap index unavailable')

    monkeypatch.setattr(conversations_db, 'find_sync_live_overlap_candidates', broken)
    incoming = {**chunk('canonical', 1000), 'client_device_id': 'synthetic-device'}
    with caplog.at_level('INFO', logger=conversations_db.logger.name):
        with pytest.raises(RuntimeError):
            conversations_db.assign_sync_conversation('synthetic-unit', incoming, firestore_client=store, timing=True)
    [line] = timing_lines(caplog)
    assert ' outcome=error ' in line and line.endswith(' exception_type=RuntimeError')
    assert ' attempts=0 ' in line and 'synthetic' not in line
