"""The write probe must count every committed write once, by collection, op and caller, and never break one."""

import asyncio
import datetime
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

firestore = pytest.importorskip('google.cloud.firestore')
from google.auth.credentials import AnonymousCredentials  # noqa: E402
from google.cloud.firestore_v1.services.firestore import FirestoreAsyncClient, FirestoreClient  # noqa: E402
from google.cloud.firestore_v1.types import (  # noqa: E402
    BatchWriteResponse,
    BeginTransactionResponse,
    CommitResponse,
    Document,
    DocumentMask,
    Precondition,
    Write,
    WriteResult,
)
from google.rpc import status_pb2  # noqa: E402

import database.firestore_document_probe as reads  # noqa: E402
import database.firestore_write_probe as probe  # noqa: E402
from database.firestore_read_origin import read_origin  # noqa: E402

ROOT = 'projects/p/databases/(default)/documents'


def _billed(collection, op, database='default'):
    value = probe.FIRESTORE_BILLED_WRITES.labels(collection=collection, op=op, database=database)._value.get()
    return float(value or 0)


def _by_origin(collection, op, origin):
    return probe.FIRESTORE_BILLED_WRITES_BY_ORIGIN.labels(collection=collection, op=op, origin=origin)._value.get()


def _by_caller(collection, op, caller):
    value = probe.FIRESTORE_BILLED_WRITES_BY_CALLER.labels(collection=collection, op=op, caller=caller)._value.get()
    return float(value or 0)


class _Transport:
    """Fake GAPIC Commit/BatchWrite: records requests, optionally fails."""

    def __init__(self):
        self.requests = []
        self.fail = False
        self.batch_status = None
        self.response = None

    def commit(self, client, request=None, **kwargs):
        if self.fail:
            raise self.fail if isinstance(self.fail, BaseException) else RuntimeError('commit refused')
        self.requests.append(request)
        if self.response is not None:
            return self.response
        writes = request['writes'] if isinstance(request, dict) else request.writes
        return CommitResponse(write_results=[WriteResult() for _ in writes])

    def batch_write(self, client, request=None, **kwargs):
        self.requests.append(request)
        return BatchWriteResponse(
            status=[status_pb2.Status(code=code) for code in self.batch_status],
            write_results=[WriteResult() for _ in self.batch_status],
        )


@pytest.fixture
def transport(monkeypatch):
    fake = _Transport()
    monkeypatch.setattr(FirestoreClient, 'commit', lambda self, request=None, **kw: fake.commit(self, request, **kw))
    monkeypatch.setattr(
        FirestoreClient, 'batch_write', lambda self, request=None, **kw: fake.batch_write(self, request, **kw)
    )

    async def async_commit(self, request=None, **kw):
        return fake.commit(self, request, **kw)

    async def async_begin(self, request=None, **kw):
        return BeginTransactionResponse(transaction=b'async-tx')

    monkeypatch.setattr(FirestoreAsyncClient, 'commit', async_commit)
    monkeypatch.setattr(FirestoreAsyncClient, 'begin_transaction', async_begin)
    monkeypatch.setattr(
        FirestoreClient, 'begin_transaction', lambda *_args, **_kw: BeginTransactionResponse(transaction=b'tx')
    )
    monkeypatch.setattr(probe, '_installed', False)
    probe.install_document_write_probe()
    yield fake


@pytest.fixture
def client(transport):
    db = firestore.Client(project='p', credentials=AnonymousCredentials())
    db._firestore_api_internal = FirestoreClient(credentials=AnonymousCredentials())
    return db


def test_write_op_classifies_every_write_shape():
    name = f'{ROOT}/users/u1/conversations/c1'
    create = Write(update=Document(name=name), current_document=Precondition(exists=False))
    assert probe.write_op(create) == ('create', 'default', ('users', 'u1', 'conversations', 'c1'))
    assert probe.write_op(Write(update=Document(name=name)))[0] == 'set'
    assert probe.write_op(Write(update=Document(name=name), update_mask=DocumentMask(field_paths=['a'])))[0] == 'merge'
    assert probe.write_op(Write(update=Document(name=name), current_document=Precondition(exists=True)))[0] == 'update'
    # A last-update-time CAS requires the document to exist: not an upsert.
    cas = Write(
        update=Document(name=name),
        update_mask=DocumentMask(field_paths=['a']),
        current_document=Precondition(update_time=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)),
    )
    assert probe.write_op(cas)[0] == 'update'
    assert probe.write_op(Write(delete=name))[0] == 'delete'
    assert probe.write_op({'delete': name})[0] == 'delete'
    named = probe.write_op(Write(delete='projects/p/databases/staging/documents/users/u1'))
    assert named == ('delete', 'named', ('users', 'u1'))
    assert probe.write_op(object()) == ('unknown', 'unknown', ())


def test_document_writes_counted_by_op_and_caller(client, transport):
    caller = f'{__name__}:test_document_writes_counted_by_op_and_caller'
    before = {op: _billed('users/conversations', op) for op in ('set', 'merge', 'update', 'create', 'delete')}
    origin = 'job:write_probe_document_test'
    expected = {'set': 2, 'update': 1, 'create': 1, 'delete': 1}
    callers_before = {op: _by_caller('users/conversations', op, caller) for op in expected}
    origins_before = {op: _by_origin('users/conversations', op, origin) for op in expected}

    ref = client.collection('users').document('u1').collection('conversations').document('c1')
    with read_origin(origin):
        ref.set({'status': 'in_progress'})
        ref.set({'status': 'completed'}, merge=True)
        ref.update({'status': 'processing'})
        ref.create({'status': 'new'})
        ref.delete()

    assert _billed('users/conversations', 'set') == before['set'] + 1
    assert _billed('users/conversations', 'merge') == before['merge'] + 1
    assert _billed('users/conversations', 'update') == before['update'] + 1
    assert _billed('users/conversations', 'create') == before['create'] + 1
    assert _billed('users/conversations', 'delete') == before['delete'] + 1
    for op, amount in expected.items():
        assert _by_caller('users/conversations', op, caller) - callers_before[op] == amount
        assert _by_origin('users/conversations', op, origin) - origins_before[op] == amount
    # The probe observes and never skips: five Commit RPCs still ran.
    assert len(transport.requests) == 5


def test_transaction_retry_helper_is_not_the_caller(client, transport, monkeypatch):
    from google.cloud.firestore_v1.types import BeginTransactionResponse

    from database.firestore_transaction_retry import run_with_transaction_contention_retry

    monkeypatch.setattr(
        FirestoreClient,
        'begin_transaction',
        lambda self, request=None, **kw: BeginTransactionResponse(transaction=b'tx'),
    )
    caller = f'{__name__}:test_transaction_retry_helper_is_not_the_caller'
    before = _by_caller('users/memories', 'set', caller)
    ref = client.collection('users').document('u1').collection('memories').document('m1')

    @firestore.transactional
    def operation(transaction):
        transaction.set(ref, {'x': 1})

    run_with_transaction_contention_retry(client.transaction, operation, operation_name='probe_test')
    assert _by_caller('users/memories', 'set', caller) == before + 1


def test_privacy_token_wrapper_preserves_writer_attribution(client, transport, monkeypatch):
    from database.batch_privacy_write_fence import _wrap_commit

    monkeypatch.setattr(FirestoreClient, 'commit', _wrap_commit(FirestoreClient.commit))
    caller = f'{__name__}:test_privacy_token_wrapper_preserves_writer_attribution'
    before = _by_caller('users/conversations', 'set', caller)
    ref = client.collection('users').document('u1').collection('conversations').document('c1')

    ref.set({'deleted': True})

    assert _by_caller('users/conversations', 'set', caller) == before + 1
    assert len(transport.requests) == 1
    # The attribution check exercises a real augmented Commit, including its token.
    assert (
        len(transport.requests[0].writes) == 4
    )  # source with folded version, Home dirty receipt/control, privacy token


def test_generic_write_helper_names_its_caller(client, transport):
    # A helper registered as (module, function) plumbing is skipped like a plumbing module.
    def _cas(ref):
        ref.set({'x': 1})

    # Same code, but its frame reports the helper's module as __name__.
    helper = types.FunctionType(_cas.__code__, {'__name__': 'utils.enrichment.outbox'}, '_cas')

    def _mutate(cas, ref):
        cas(ref)

    # The outbox adapter's _mutate sits in front of the CAS helper; both are skipped.
    adapter = types.FunctionType(_mutate.__code__, {'__name__': 'database.outbox_firestore'}, '_mutate')
    caller = f'{__name__}:test_generic_write_helper_names_its_caller'
    before = _by_caller('users/memories', 'set', caller)
    helper(client.collection('users').document('u1').collection('memories').document('m1'))
    adapter(helper, client.collection('users').document('u1').collection('memories').document('m2'))
    assert _by_caller('users/memories', 'set', caller) == before + 2


def test_deadline_and_projection_runners_name_caller(client, transport):
    # rpc_deadline.bounded wraps every client API call; ProjectionStore.run wraps every
    # projection transaction. Neither may become the caller label.
    def bounded(ref):
        ref.set({'x': 1})

    wrapper = types.FunctionType(bounded.__code__, {'__name__': 'database.rpc_deadline'}, 'bounded')

    def run(write, ref):
        write(ref)

    runner = types.FunctionType(run.__code__, {'__name__': 'database.batch_pipeline_projection'}, 'run')
    caller = f'{__name__}:test_deadline_and_projection_runners_name_caller'
    before = _by_caller('users/memories', 'set', caller)
    wrapper(client.collection('users').document('u1').collection('memories').document('m1'))
    runner(wrapper, client.collection('users').document('u1').collection('memories').document('m2'))
    assert _by_caller('users/memories', 'set', caller) == before + 2


def test_batch_counts_each_write_and_failed_commit_counts_nothing(client, transport):
    before = _billed('users/memories', 'set')
    batch = client.batch()
    for i in range(3):
        batch.set(client.collection('users').document('u1').collection('memories').document(f'm{i}'), {'x': i})
    batch.commit()
    assert _billed('users/memories', 'set') == before + 3

    transport.fail = True
    failed = client.batch()
    failed.set(client.collection('users').document('u1').collection('memories').document('m9'), {'x': 9})
    with pytest.raises(RuntimeError):
        failed.commit()
    assert _billed('users/memories', 'set') == before + 3


def test_ambiguous_commit_is_counted_apart(client, transport):
    from google.api_core.exceptions import DeadlineExceeded, InvalidArgument

    billed = _billed('users/memories', 'set')
    ambiguous = probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get()
    ref = client.collection('users').document('u1').collection('memories').document('m1')

    transport.fail = DeadlineExceeded('response lost')
    with pytest.raises(DeadlineExceeded):
        ref.set({'x': 1}, retry=None)
    assert probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get() == ambiguous + 1

    # A definite rejection applied nothing and is not ambiguous.
    transport.fail = InvalidArgument('rejected')
    with pytest.raises(InvalidArgument):
        ref.set({'x': 1}, retry=None)
    assert probe.FIRESTORE_AMBIGUOUS_COMMIT_WRITES._value.get() == ambiguous + 1
    assert _billed('users/memories', 'set') == billed


def test_noop_writes_are_counted_by_caller(client, transport):
    caller = f'{__name__}:test_noop_writes_are_counted_by_caller'
    noop_before = probe.FIRESTORE_NOOP_WRITES_BY_CALLER.labels(collection='users/memories', caller=caller)._value.get()
    committed = datetime.datetime(2026, 11, 1, 12, tzinfo=datetime.timezone.utc)
    earlier = committed - datetime.timedelta(hours=3)
    transport.response = CommitResponse(
        commit_time=committed,
        write_results=[WriteResult(update_time=committed), WriteResult(update_time=earlier), WriteResult()],
    )
    memories = client.collection('users').document('u1').collection('memories')
    batch = client.batch()
    batch.set(memories.document('changed'), {'x': 1})
    batch.set(memories.document('unchanged'), {'x': 1})
    batch.delete(memories.document('gone'))
    batch.commit()
    # Only the write whose update_time predates commit_time is a no-op; a delete has none.
    noop = probe.FIRESTORE_NOOP_WRITES_BY_CALLER.labels(collection='users/memories', caller=caller)._value.get()
    assert noop == noop_before + 1


def test_batch_write_counts_only_applied_writes(transport):
    before = _billed('users/memories', 'delete')
    transport.batch_status = [0, 10, 0]
    request = {'writes': [Write(delete=f'{ROOT}/users/u1/memories/m{i}') for i in range(3)]}
    FirestoreClient.batch_write(object(), request=request)
    assert _billed('users/memories', 'delete') == before + 2


def test_transaction_counts_staged_writes_once(client, transport):
    from google.api_core.exceptions import Aborted

    ref = client.document('users/u1/memories/m1')
    caller = f'{__name__}:test_transaction_counts_staged_writes_once'
    before = {op: _by_caller('users/memories', op, caller) for op in ('create', 'update', 'delete', 'set')}
    # Abort the first decorated commit and allow the SDK to retry it.
    transport.fail = Aborted('retry transaction')
    attempts = 0

    @firestore.transactional
    def operation(transaction):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            transport.fail = False
        transaction.create(ref, {'x': 1})
        transaction.set(ref, {'y': 1}, merge=True)
        transaction.update(ref, {'x': firestore.Increment(1)})
        transaction.delete(ref)
        assert {op: _by_caller('users/memories', op, caller) for op in before} == before

    operation(client.transaction())
    assert attempts == 2
    assert len(transport.requests) == 1
    assert len(transport.requests[0]['writes']) == 4
    for op, count in before.items():
        assert _by_caller('users/memories', op, caller) == count + 1


@pytest.mark.parametrize('source', [firestore.Client, firestore.AsyncClient])
def test_bulk_writer_tracks_each_submitter_through_worker_and_retry(transport, source):
    from google.cloud.firestore_v1.bulk_writer import BulkRetry, BulkWriterOptions

    db = source(project='p', credentials=AnonymousCredentials())
    writer = db.bulk_writer(options=BulkWriterOptions(retry=BulkRetry.immediate))
    collection = db.collection('users/u1/memories')
    transport.batch_status = [0, 10, 7]

    def submit_first():
        with read_origin('job:bulk_first'):
            writer.create(collection.document('m1'), {'x': 1})

    def submit_second():
        with read_origin('job:bulk_second'):
            writer.update(collection.document('m2'), {'x': 2})
            writer.delete(collection.document('m3'))

    def retry_only_aborted(error, _writer):
        if error.code == 10:
            transport.batch_status = [0]
            return True
        return False

    before_create = _by_caller('users/memories', 'create', f'{__name__}:submit_first')
    before_update = _by_caller('users/memories', 'update', f'{__name__}:submit_second')
    before_delete = _by_caller('users/memories', 'delete', f'{__name__}:submit_second')
    origins = (
        _by_origin('users/memories', 'create', 'job:bulk_first'),
        _by_origin('users/memories', 'update', 'job:bulk_second'),
        _by_origin('users/memories', 'delete', 'job:bulk_second'),
    )
    writer.on_write_error(retry_only_aborted)
    submit_first()
    submit_second()
    assert not transport.requests
    with read_origin('job:bulk_flusher'):
        writer.flush()
    writer.close()
    assert len(transport.requests) == 2
    assert _by_caller('users/memories', 'create', f'{__name__}:submit_first') == before_create + 1
    assert _by_caller('users/memories', 'update', f'{__name__}:submit_second') == before_update + 1
    assert _by_caller('users/memories', 'delete', f'{__name__}:submit_second') == before_delete
    assert _by_origin('users/memories', 'create', 'job:bulk_first') == origins[0] + 1
    assert _by_origin('users/memories', 'update', 'job:bulk_second') == origins[1] + 1
    assert _by_origin('users/memories', 'delete', 'job:bulk_second') == origins[2]


def test_serial_bulk_retry_does_not_leak_origin_into_callbacks(client, transport):
    from google.cloud.firestore_v1.bulk_writer import BulkRetry, BulkWriterOptions, SendMode

    writer = client.bulk_writer(options=BulkWriterOptions(mode=SendMode.serial, retry=BulkRetry.immediate))
    writer.batch_size = 1
    first = client.document('users/u1/memories/first')
    second = client.document('users/u1/memories/second')
    transport.batch_status = [10]

    def on_error(_error, _writer):
        transport.batch_status = [0]
        return True

    def on_success(reference, _result, writer):
        if reference == first:
            with read_origin('job:serial_bulk_callback'):
                writer.set(second, {'x': 2})

    def submit():
        with read_origin('job:serial_bulk_submit'):
            writer.set(first, {'x': 1})

    writer.on_write_error(on_error)
    writer.on_write_result(on_success)
    submit_origin = _by_origin('users/memories', 'set', 'job:serial_bulk_submit')
    callback_origin = _by_origin('users/memories', 'set', 'job:serial_bulk_callback')
    callback_caller = _by_caller('users/memories', 'set', f'{__name__}:on_success')
    submit()
    writer.close()

    assert len(transport.requests) == 3
    assert _by_origin('users/memories', 'set', 'job:serial_bulk_submit') == submit_origin + 1
    assert _by_origin('users/memories', 'set', 'job:serial_bulk_callback') == callback_origin + 1
    assert _by_caller('users/memories', 'set', f'{__name__}:on_success') == callback_caller + 1


def test_async_document_batch_and_transaction_count_once(transport):
    client = firestore.AsyncClient(project='p', credentials=AnonymousCredentials())
    ref = client.document('users/u1/memories/m1')
    origin = 'job:async_write_probe'
    expected = {'set': 4, 'create': 1, 'update': 2, 'delete': 3}
    before = {op: _by_origin('users/memories', op, origin) for op in expected}

    @firestore.async_transactional
    async def operation(transaction):
        transaction.set(ref, {'a': 1})
        transaction.set(ref, {'a': 2}, merge=True)
        transaction.update(ref, {'a': 3})
        transaction.delete(ref)

    async def write():
        with read_origin(origin):
            await ref.set({'a': 1})
            await ref.create({'a': 1})
            await ref.update({'a': 2})
            await ref.delete()
            batch = client.batch()
            batch.set(ref, {'a': 3}, merge=True)
            batch.delete(ref)
            await batch.commit()
            await operation(client.transaction())

    asyncio.run(write())
    assert len(transport.requests) == 6
    for op, amount in expected.items():
        assert _by_origin('users/memories', op, origin) - before[op] == amount


def test_probe_sees_writes_a_later_commit_patch_appends(transport):
    # database._client installs the probe before memory_change_head, so the head
    # wrapper calls through the probe with its head write already appended.
    from database import memory_change_head

    head_wrapped = memory_change_head._wrap_commit(FirestoreClient.commit)
    source_before = _billed('users/memories', 'merge')
    head_before = _billed('other', 'merge') + _billed('users/memory_state', 'merge')
    write = Write(update=Document(name=f'{ROOT}/users/u1/memories/m1'), update_mask=DocumentMask(field_paths=['a']))
    head_wrapped(object(), request={'database': 'projects/p/databases/(default)', 'writes': [write]})
    assert _billed('users/memories', 'merge') == source_before + 1
    assert _billed('other', 'merge') + _billed('users/memory_state', 'merge') == head_before + 1
    assert len(transport.requests[-1].writes) == 2


def test_recording_failure_never_propagates(client, transport, monkeypatch):
    class _Exploding:
        def labels(self, **kwargs):
            raise RuntimeError('registry unavailable')

    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES', _Exploding())
    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES_BY_CALLER', _Exploding())
    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES_BY_ORIGIN', _Exploding())
    client.collection('users').document('u1').set({'a': 1})
    assert len(transport.requests) == 1


@pytest.mark.parametrize('is_async', [False, True], ids=['sync', 'async'])
def test_successful_commit_response_survives_counter_and_warning_failures(transport, monkeypatch, is_async):
    class _Counter:
        def inc(self, _amount):
            raise OSError('counter unavailable')

    class _Metric:
        def labels(self, **_kwargs):
            return _Counter()

    write = Write(update=Document(name=f'{ROOT}/users/u1/memories/m1'))
    request = {'database': 'projects/p/databases/(default)', 'writes': [write]}
    transport.response = CommitResponse(write_results=[WriteResult()])
    monkeypatch.setattr(probe, 'FIRESTORE_BILLED_WRITES', _Metric())

    with patch.object(probe.logger, 'warning', side_effect=OSError('logger unavailable')):
        if is_async:
            response = asyncio.run(FirestoreAsyncClient.commit(object(), request=request))
        else:
            response = FirestoreClient.commit(object(), request=request)

    assert transport.requests == [request]
    assert response is transport.response


@pytest.mark.parametrize('is_async', [False, True], ids=['sync', 'async'])
def test_successful_commit_response_is_returned_when_request_tally_raises(transport, is_async):
    write = Write(update=Document(name=f'{ROOT}/users/u1/memories/m1'))
    request = {'database': 'projects/p/databases/(default)', 'writes': [write]}
    transport.response = CommitResponse(write_results=[WriteResult()])
    before = _billed('users/memories', 'set')

    with (
        probe.count_committed_writes() as tally,
        patch.object(probe.CommittedWrites, 'add', side_effect=OSError('tally unavailable')) as add,
    ):
        if is_async:
            response = asyncio.run(FirestoreAsyncClient.commit(object(), request=request))
        else:
            response = FirestoreClient.commit(object(), request=request)

    assert transport.requests == [request]
    add.assert_called_once_with(1)
    assert response is transport.response
    assert _billed('users/memories', 'set') - before == 1
    with pytest.raises(RuntimeError, match='Firestore write tally incomplete'):
        _ = tally.total


def test_install_is_idempotent(transport):
    wrapped = FirestoreClient.commit
    probe._installed = False
    probe.install_document_write_probe()
    assert FirestoreClient.commit is wrapped


@pytest.mark.parametrize('value', ['false', ' FALSE '])
@pytest.mark.parametrize('key', ['FIRESTORE_WRITE_PROBE_ENABLED', 'OMI_FIRESTORE_WRITE_PROBE_ENABLED'])
def test_kill_switch_leaves_the_transport_unwrapped(monkeypatch, key, value):
    def commit(self, request=None, **kwargs):
        return CommitResponse()

    monkeypatch.setattr(FirestoreClient, 'commit', commit)
    monkeypatch.setattr(probe, '_installed', False)
    monkeypatch.setenv(key, value)
    probe.install_document_write_probe()
    assert FirestoreClient.commit is commit
    assert probe._installed is False


@pytest.mark.parametrize('value', [None, '', 'true', '0', 'off'])
def test_kill_switch_is_on_unless_literal_false(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('OMI_FIRESTORE_WRITE_PROBE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('OMI_FIRESTORE_WRITE_PROBE_ENABLED', value)
    assert probe.probe_enabled() is True


def test_caller_cap_folds_new_labels_to_other(client, monkeypatch):
    monkeypatch.setattr(reads, '_known_callers', {f'm{i}:f' for i in range(reads.MAX_CALLERS)})
    overflow = reads.FIRESTORE_CALLER_LABEL_OVERFLOW._value.get()
    write_overflow = probe.FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW._value.get()
    before = _by_caller('users/memories', 'set', 'other')
    client.document('users/u1/memories/m1').set({'x': 1})
    assert _by_caller('users/memories', 'set', 'other') == before + 1
    assert reads.FIRESTORE_CALLER_LABEL_OVERFLOW._value.get() == overflow + 1
    assert probe.FIRESTORE_WRITE_CALLER_LABEL_OVERFLOW._value.get() == write_overflow + 1


@pytest.mark.parametrize('method', ['commit', 'batch_write'])
def test_batch_privacy_fence_preserves_writer_attribution(client, transport, monkeypatch, method):
    from database import batch_privacy_write_fence as fence

    monkeypatch.setattr(FirestoreClient, 'commit', fence._wrap_commit(FirestoreClient.commit))
    monkeypatch.setattr(FirestoreClient, 'batch_write', fence._wrap_bulk(FirestoreClient.batch_write))
    caller = f'{__name__}:test_batch_privacy_fence_preserves_writer_attribution'
    source_before = _by_caller('users/conversations', 'set', caller)
    token_before = _by_caller('batch_pipeline_privacy', 'set', caller)
    if method == 'commit':
        client.document('users/u1/conversations/c1').set({'record_lane_owner': 'batch_live_v1'})
    else:
        client._firestore_api.batch_write(
            request={
                'database': client._database_string,
                'writes': [Write(update=Document(name=f'{ROOT}/users/u1/conversations/c1'))],
            }
        )
    assert _by_caller('users/conversations', 'set', caller) == source_before + 1
    assert _by_caller('batch_pipeline_privacy', 'set', caller) == token_before + 1
    assert len(transport.requests) == 1
    assert (
        len(transport.requests[0].writes) == 4
    )  # source with folded version, Home dirty receipt/control, privacy token


@pytest.mark.parametrize(
    'parts,expected',
    [
        (('users', 'u' * 28, 'deleted_conversations', 'private-conversation'), 'users/deleted_conversations'),
        (('batch_pipeline_privacy', 'private-owner-token'), 'batch_pipeline_privacy'),
        (('legal_holds', 'u' * 28), 'legal_holds'),
        (('legal_hold_deletion_gates', 'u' * 28), 'legal_hold_deletion_gates'),
    ],
)
def test_privacy_authority_labels_drop_document_identifiers(parts, expected):
    assert probe.collection_pattern(parts) == expected
