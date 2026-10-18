"""Worker review regressions, including real SDK traffic to a loopback query stub.

The gRPC stub implements the RunQuery ordering/cursor subset used here. This
checks SDK serialization over the emulator transport; it is not the Java
Firestore emulator and does not establish index readiness or transaction safety.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import Document, RunQueryRequest, RunQueryResponse, StructuredQuery, Value
import grpc
import pytest

from utils import processing_backlog_worker as worker


def snapshot(identity, **row):
    return SimpleNamespace(id=identity, to_dict=lambda: dict(row))


def protocol_value(value):
    """Firestore ordering for the numeric/timestamp/reference types under test."""
    proto = Value.pb(value)
    kind = proto.WhichOneof('value_type')
    if kind == 'timestamp_value':
        return 3, (proto.timestamp_value.seconds, proto.timestamp_value.nanos)
    if kind == 'reference_value':
        return 6, proto.reference_value
    if kind in {'double_value', 'integer_value'}:
        return 2, getattr(proto, kind)
    raise AssertionError(f'Unexpected cursor type: {kind}')


@pytest.fixture
def query_protocol(monkeypatch):
    """Real SDK + loopback gRPC, isolated from all actual customer databases."""
    documents, requests = {}, []

    def run_query(request, context):
        query = request.structured_query
        requests.append(request)
        collection = request.parent + '/' + query.from_[0].collection_id
        rows = [(path, row) for path, row in documents.items() if path.rsplit('/', 1)[0] == collection]
        # The server supplies the implicit name order, but a timestamp-only
        # cursor is still a prefix: start_after excludes all equal timestamps.
        orders = list(query.order_by)
        if not any(order.field.field_path == '__name__' for order in orders):
            orders.append(
                StructuredQuery.Order(
                    field=StructuredQuery.FieldReference(field_path='__name__'), direction=orders[-1].direction
                )
            )
        assert all(order.direction == StructuredQuery.Direction.DESCENDING for order in orders)

        def key(path, row):
            return tuple(
                protocol_value(
                    Value(reference_value=path)
                    if order.field.field_path == '__name__'
                    else _helpers.encode_value(row[order.field.field_path])
                )
                for order in orders
            )

        rows.sort(key=lambda entry: key(*entry), reverse=True)
        if query.start_at.values:
            assert query.start_at.before is False
            cursor = tuple(protocol_value(value) for value in query.start_at.values)
            rows = [entry for entry in rows if key(*entry)[: len(cursor)] < cursor]
        for path, row in rows[: query.limit]:
            yield RunQueryResponse(document=Document(name=path, fields=_helpers.encode_dict(row)))

    executor = ThreadPoolExecutor(max_workers=1)
    server = grpc.server(executor)
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                'google.firestore.v1.Firestore',
                {
                    'RunQuery': grpc.unary_stream_rpc_method_handler(
                        run_query,
                        request_deserializer=RunQueryRequest.deserialize,
                        response_serializer=RunQueryResponse.serialize,
                    )
                },
            ),
        )
    )
    port = server.add_insecure_port('127.0.0.1:0')
    assert port
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', f'127.0.0.1:{port}')
    server.start()
    client = firestore.Client(project='demo-processing-backlog-review', credentials=AnonymousCredentials())
    try:
        yield client, documents, requests
    finally:
        client.close()
        server.stop(0).wait(timeout=5)
        executor.shutdown(wait=True)


@pytest.mark.parametrize('kind', ['audio', 'text'])
@pytest.mark.parametrize(
    'timestamp', [1000.0, DatetimeWithNanoseconds(2026, 10, 1, nanosecond=123456000, tzinfo=timezone.utc)]
)
def test_equal_timestamp_pages_reach_every_sibling_through_sdk_protocol(monkeypatch, query_protocol, kind, timestamp):
    client, documents, requests = query_protocol
    collection = client.collection('users').document('synthetic').collection(kind)
    monkeypatch.setattr(
        worker.cap_hold if kind == 'audio' else worker.store,
        'holds' if kind == 'audio' else 'items',
        lambda uid: collection,
    )
    field = 'listed_at' if kind == 'audio' else 'started_at'
    identities = [f'capture-{index:03}' for index in range(worker.PAGE * 2 + 3)]
    for identity in identities:
        documents[collection.document(identity)._document_path] = {field: timestamp, 'state': 'held'}

    # Reproduce the old builder through the same SDK/transport. The mapping's
    # extra __name__ is dropped; the second page skips all remaining siblings.
    old_query = collection.order_by(field, direction=firestore.Query.DESCENDING)
    old_first = list(old_query.limit(worker.PAGE).stream())
    old_second = list(
        old_query.start_after({field: timestamp, '__name__': old_first[-1].reference}).limit(worker.PAGE).stream()
    )
    assert len(old_first) == worker.PAGE and old_second == []
    assert len(requests[-1].structured_query.start_at.values) == 1

    requests.clear()
    seen, cursor = [], None
    for _ in range(5):
        page = worker._page('synthetic', kind, cursor)
        if not page:
            break
        seen.extend(snap.id for _, snap in page)
        candidate = worker._candidate(*page[-1])
        cursor = {'at': candidate['at'], 'id': candidate['id']}
    else:
        pytest.fail('Cursor failed to terminate')
    assert seen == sorted(identities, reverse=True)
    assert len(set(seen)) == len(identities)
    for request in requests:
        query = request.structured_query
        assert [order.field.field_path for order in query.order_by] == [field, '__name__']
        if query.start_at.values:
            assert len(query.start_at.values) == 2
            assert protocol_value(query.start_at.values[0]) == protocol_value(_helpers.encode_value(timestamp))
            assert query.start_at.values[1].reference_value.startswith(collection._parent_info()[0] + '/')


@pytest.fixture
def job_harness(monkeypatch):
    real_page = worker._page
    job = {
        'state': 'processing',
        'period': '2026-10',
        'token': 'choice',
        'lease': 'lease',
        'lease_until': 1,
        'cutoff': 100,
        'remaining': 10,
        'reserved': {},
    }
    processed, pauses, scheduled = [], [], []
    monkeypatch.setattr(worker.funded_processing, 'enabled', lambda: True)
    monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: '2026-10')
    monkeypatch.setattr(worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True))
    monkeypatch.setattr(worker.funded_processing, 'capacity', lambda current: (100, 100))
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: deepcopy(job))

    def claim(uid, token, period):
        job['lease_until'] = worker.time.time() + 1800
        return 'lease'

    def fenced(token, lease):
        return job['token'] == token and job['lease'] == lease and job['lease_until'] > worker.time.time()

    def checkpoint(uid, token, lease, updates):
        if not fenced(token, lease):
            return False
        job.update(deepcopy(updates))
        return True

    def pause(uid, token, lease):
        pauses.append((uid, token, lease))
        if not fenced(token, lease) or job.get('reserved'):
            return False
        job.update(state='waiting_choice', lease_until=0)
        return True

    def finish(uid, token, lease, period):
        assert fenced(token, lease)
        job.update(state='waiting_choice', lease_until=0)
        return False

    async def run_blocking(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    async def process(uid, item):
        processed.append(deepcopy(item))
        return True

    def schedule(coroutine, *, name):
        if name == 'processing_backlog_continuation':
            scheduled.append(name)
            coroutine.close()
            return None
        return asyncio.create_task(coroutine)

    monkeypatch.setattr(worker.store, 'claim', claim)
    monkeypatch.setattr(worker.store, 'checkpoint', checkpoint)
    monkeypatch.setattr(worker.store, 'finish', finish)
    # The store helper belongs to root's lane. This fake exercises worker
    # composition; root separately verifies the actual transaction predicate.
    monkeypatch.setattr(worker.store, 'pause_if_unreserved', pause, raising=False)
    monkeypatch.setattr(worker, 'run_blocking', run_blocking)
    monkeypatch.setattr(worker, 'start_background_task', schedule)
    monkeypatch.setattr(worker, '_process', process)
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    return SimpleNamespace(
        job=job,
        processed=processed,
        pauses=pauses,
        scheduled=scheduled,
        checkpoint=checkpoint,
        real_page=real_page,
    )


@pytest.mark.parametrize('audio_timestamp', [False, True])
async def test_worker_merges_multiple_equal_timestamp_pages_without_drops_or_double_debits(
    monkeypatch, query_protocol, job_harness, audio_timestamp
):
    client, documents, requests = query_protocol
    harness = job_harness
    harness.job['remaining'] = 10000
    collections = {
        kind: client.collection('users').document('synthetic').collection(kind) for kind in ('audio', 'text')
    }
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: collections['audio'])
    monkeypatch.setattr(worker.store, 'items', lambda uid: collections['text'])
    monkeypatch.setattr(worker, '_page', harness.real_page)
    expected = []
    for index in range(worker.PAGE * 2 + 3):
        for kind in ('audio', 'text'):
            identity = f'capture-{index:03}-{kind}'
            at = datetime.fromtimestamp(1000, tz=timezone.utc) if kind == 'audio' and audio_timestamp else 1000.0
            field = 'listed_at' if kind == 'audio' else 'started_at'
            documents[collections[kind].document(identity)._document_path] = {
                field: at,
                'state': 'held',
                'created_at': 50,
                'queued_at': 50,
                'units': 1,
            }
            expected.append((kind, identity))
    for _ in range(10):
        await worker.run('synthetic', continuation=True)
        if harness.job['state'] == 'waiting_choice':
            break
    else:
        pytest.fail('Worker failed to finish bounded continuation pages')
    actual = [(item['kind'], item['id']) for item in harness.processed]
    assert actual == sorted(expected, key=lambda item: item[1], reverse=True)
    assert len(set(actual)) == len(expected)
    assert harness.job['remaining'] == 10000 - sum(item['units'] for item in harness.processed)
    assert harness.job['reserved'] == {} and harness.pauses == []
    assert isinstance(harness.job['cursor_audio']['at'], datetime if audio_timestamp else float)
    assert isinstance(harness.job['cursor_text']['at'], float)
    assert len(harness.scheduled) >= 4


async def test_flags_off_worker_does_not_read_or_schedule(monkeypatch):
    monkeypatch.setattr(worker.funded_processing, 'enabled', lambda: False)
    blocked = Mock(side_effect=AssertionError('Flag-off worker touched IO/scheduling'))
    monkeypatch.setattr(worker, 'run_blocking', blocked)
    monkeypatch.setattr(worker, 'start_background_task', blocked)
    await worker.run('synthetic')
    worker.kick('synthetic')
    blocked.assert_not_called()


@pytest.mark.parametrize('naive', [False, True])
async def test_mixed_datetime_numeric_queues_sort_and_compare_without_changing_cursor_types(
    monkeypatch, job_harness, naive
):
    harness = job_harness

    def timestamp(seconds):
        value = DatetimeWithNanoseconds.fromtimestamp(seconds, tz=timezone.utc)
        return value.replace(tzinfo=None) if naive else value

    harness.job['cutoff'] = timestamp(100)
    rows = {
        'audio': [
            ('audio', snapshot('audio-new', listed_at=timestamp(120), created_at=50, seconds=1)),
            ('audio', snapshot('audio-old', listed_at=timestamp(60), created_at=timestamp(5), seconds=1)),
        ],
        'text': [
            ('text', snapshot('after-choice', started_at=timestamp(200), queued_at=timestamp(101), units=1)),
            ('text', snapshot('text-middle', started_at=100.0, queued_at=40, units=1)),
        ],
    }
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: rows[kind])
    monkeypatch.setattr(worker.cap_hold, 'remaining_seconds', lambda row: 0)
    await worker.run('synthetic')
    assert [item['id'] for item in harness.processed] == ['audio-new', 'text-middle', 'audio-old']
    assert harness.job['state'] == 'waiting_choice'
    assert harness.job['cursor_audio']['at'] == timestamp(60)
    assert isinstance(harness.job['cursor_audio']['at'], datetime)
    assert harness.job['cursor_text']['at'] == 100.0
    assert isinstance(harness.job['cursor_text']['at'], float)
    assert harness.pauses == []


@pytest.mark.parametrize('kind', ['audio', 'text'])
async def test_query_failure_returns_unreserved_choice_to_waiting(monkeypatch, job_harness, kind):
    harness = job_harness

    def page(uid, queue, cursor):
        if queue == kind:
            raise RuntimeError('Synthetic query rejection')
        return []

    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic')
    assert harness.job['state'] == 'waiting_choice'
    assert harness.job['lease_until'] == 0 and harness.job['reserved'] == {}
    assert harness.pauses == [('synthetic', 'choice', 'lease')]
    assert harness.processed == []


async def test_allowance_failure_before_reservation_returns_to_choice(monkeypatch, job_harness):
    harness = job_harness
    row = ('text', snapshot('capture', started_at=20, queued_at=10, units=3))
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [row] if kind == 'text' else [])
    monkeypatch.setattr(worker.funded_processing, 'allowance', Mock(side_effect=RuntimeError('Allowance unavailable')))
    await worker.run('synthetic')
    assert harness.job['state'] == 'waiting_choice'
    assert harness.job['remaining'] == 10 and harness.job['reserved'] == {}
    assert harness.processed == []


async def test_processing_exception_retries_same_reserved_identity_without_second_debit(monkeypatch, job_harness):
    harness = job_harness
    row = ('text', snapshot('capture', started_at=20, queued_at=10, units=3))
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [row] if kind == 'text' and not cursor else [])
    attempts = []

    async def process(uid, item):
        attempts.append(deepcopy(item))
        if len(attempts) == 1:
            raise RuntimeError('Application response lost')
        return True

    monkeypatch.setattr(worker, '_process', process)
    await worker.run('synthetic')
    reserved = deepcopy(harness.job['reserved'])
    assert reserved['id'] == 'capture'
    assert harness.job['state'] == 'processing' and harness.job['remaining'] == 7
    assert harness.job['lease_until'] == 0
    await worker.run('synthetic', continuation=True)
    assert attempts == [reserved, reserved]
    assert harness.job['remaining'] == 7 and harness.job['reserved'] == {}
    assert harness.job['state'] == 'waiting_choice'


async def test_committed_reservation_with_lost_checkpoint_response_is_not_replaced(monkeypatch, job_harness):
    harness = job_harness
    row = ('text', snapshot('capture', started_at=20, queued_at=10, units=3))
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [row] if kind == 'text' and not cursor else [])

    def checkpoint(uid, token, lease, updates):
        result = harness.checkpoint(uid, token, lease, updates)
        if updates.get('reserved'):
            raise RuntimeError('Committed checkpoint response lost')
        return result

    monkeypatch.setattr(worker.store, 'checkpoint', checkpoint)
    await worker.run('synthetic')
    assert harness.job['state'] == 'processing' and harness.job['remaining'] == 7
    assert harness.job['reserved']['id'] == 'capture'
    assert harness.processed == []
    monkeypatch.setattr(worker.store, 'checkpoint', harness.checkpoint)
    await worker.run('synthetic', continuation=True)
    assert [item['id'] for item in harness.processed] == ['capture']
    assert harness.job['remaining'] == 7 and harness.job['state'] == 'waiting_choice'


async def test_query_failure_after_successful_reserved_retry_returns_to_choice(monkeypatch, job_harness):
    harness = job_harness
    harness.job.update(reserved={'kind': 'text', 'id': 'already-debited', 'units': 3}, remaining=7)
    monkeypatch.setattr(worker, '_page', Mock(side_effect=RuntimeError('Query rejected after application')))
    await worker.run('synthetic')
    assert [item['id'] for item in harness.processed] == ['already-debited']
    assert harness.job['reserved'] == {} and harness.job['remaining'] == 7
    assert harness.job['state'] == 'waiting_choice'


async def test_exception_cleanup_cannot_pause_newer_token(monkeypatch, job_harness):
    harness = job_harness

    def page(*args):
        harness.job.update(token='new-choice', lease='new-lease')
        raise RuntimeError('Worker superseded during query')

    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic')
    assert harness.job['state'] == 'processing' and harness.job['token'] == 'new-choice'
    assert harness.job['lease'] == 'new-lease' and harness.job['lease_until'] > worker.time.time()
    assert harness.pauses == [('synthetic', 'choice', 'lease')]
