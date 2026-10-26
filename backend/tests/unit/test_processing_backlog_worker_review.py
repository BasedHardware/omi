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
from unittest.mock import AsyncMock, Mock

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import Document, RunQueryRequest, RunQueryResponse, StructuredQuery, Value
import grpc
import pytest

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

from utils import processing_backlog_worker as worker


@pytest.fixture(autouse=True)
def no_cap_hold_reservations(monkeypatch):
    # Cap-hold batch reservations (lane 6) are covered by test_cap_hold_batch_debit.py; here none are open.
    monkeypatch.setattr(worker.cap_hold_reservations, 'open_units', lambda *args, **kwargs: 0.0)


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
    real_process = worker._process
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
    processed, finishes, scheduled = [], [], []
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync,batch')
    monkeypatch.setattr(worker, '_selected', AsyncMock(return_value=True))
    monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: '2026-10')
    monkeypatch.setattr(worker.funded_processing, 'allowance', lambda uid: SimpleNamespace(managed=True))
    monkeypatch.setattr(worker.funded_processing, 'capacity', lambda current: (100, 100))
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: deepcopy(job))

    def claim(uid, token, period):
        if job['state'] != 'processing' or job['token'] != token or job['period'] != period:
            return None
        job['lease_until'] = worker.time.time() + 1800
        return 'lease'

    def fenced(token, lease):
        return job['token'] == token and job['lease'] == lease and job['lease_until'] > worker.time.time()

    def checkpoint(uid, token, lease, updates):
        if not fenced(token, lease):
            return False
        job.update(deepcopy(updates))
        return True

    def finish(uid, token, lease, period):
        finishes.append((uid, token, lease, period))
        if not fenced(token, lease) or job.get('reserved'):
            return False
        pending = job.get('pending_upgrade') or {}
        if pending.get('period') == period == job['period']:
            job.update(
                state='processing',
                token='upgrade-choice',
                remaining=pending['remaining'],
                cutoff=pending['cutoff'],
                pending_upgrade={},
                reserved={},
                scope_skipped=False,
                cursor_audio=None,
                cursor_text=None,
                lease_until=0,
            )
            return True
        if job.get('scope_skipped'):
            job.update(cursor_audio=None, cursor_text=None, scope_skipped=False, lease_until=0)
            return False
        job.update(state='waiting_choice', pending_upgrade={}, lease_until=0)
        return False

    async def run_blocking(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    async def process(uid, item):
        processed.append(deepcopy(item))
        return worker.AttemptOutcome.COMPLETE

    monkeypatch.setattr(worker.store, 'claim', claim)
    monkeypatch.setattr(worker.store, 'checkpoint', checkpoint)
    monkeypatch.setattr(worker.store, 'finish', finish)
    # This fake exercises worker composition. Root's lane separately verifies
    # the actual finish transaction's reservation and pending-upgrade predicates.
    monkeypatch.setattr(worker, 'run_blocking', run_blocking)
    monkeypatch.setattr(worker, '_process', process)
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    return SimpleNamespace(
        job=job,
        processed=processed,
        finishes=finishes,
        scheduled=scheduled,
        checkpoint=checkpoint,
        real_page=real_page,
        real_process=real_process,
        claim=claim,
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
    assert harness.job['reserved'] == {} and len(harness.finishes) == 1
    assert isinstance(harness.job['cursor_audio']['at'], datetime if audio_timestamp else float)
    assert isinstance(harness.job['cursor_text']['at'], float)
    assert harness.scheduled == []  # Repeated durable sweeps drive the pages.


async def test_flags_off_worker_does_not_read_or_schedule(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    blocked = Mock(side_effect=AssertionError('Flag-off worker touched IO/scheduling'))
    monkeypatch.setattr(worker, 'run_blocking', blocked)
    await worker.run('synthetic')
    blocked.assert_not_called()


async def test_resumed_reservation_consumes_single_candidate_rotation_turn(monkeypatch, job_harness):
    reserved = {'kind': 'audio', 'id': 'reserved', 'units': 1, 'at': 100}
    job_harness.job['reserved'] = reserved
    page = Mock(side_effect=AssertionError('owner took a second candidate in one turn'))
    monkeypatch.setattr(worker, '_page', page)
    assert await worker.run('synthetic', max_items=1)
    assert job_harness.processed == [reserved]
    assert job_harness.job['reserved'] == {}
    assert job_harness.job['state'] == 'processing'
    page.assert_not_called()


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
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]


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
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]
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
        return worker.AttemptOutcome.COMPLETE

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


async def test_exception_cleanup_cannot_finish_newer_token(monkeypatch, job_harness):
    harness = job_harness

    def page(*args):
        harness.job.update(token='new-choice', lease='new-lease')
        raise RuntimeError('Worker superseded during query')

    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic')
    assert harness.job['state'] == 'processing' and harness.job['token'] == 'new-choice'
    assert harness.job['lease'] == 'new-lease' and harness.job['lease_until'] > worker.time.time()
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]
    assert harness.scheduled == []


def conversation_row(identity='capture'):
    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return {
        'id': identity,
        'created_at': at,
        'started_at': at,
        'finished_at': at,
        'structured': {},
        'processing_deferred': True,
    }


@pytest.mark.parametrize('condition', ['missing', 'deleted', 'done', 'busy', 'deferred', 'complete'])
def test_text_attempt_reports_known_completion_separately_from_busy_lease(monkeypatch, condition):
    row = conversation_row()
    if condition == 'missing':
        row = None
    elif condition == 'deleted':
        row['deleted'] = True
    elif condition == 'done':
        row['processing_deferred'] = False
    monkeypatch.setattr(worker.conversations_db, 'get_conversation', lambda *args: row)
    claim = Mock(return_value=None if condition == 'busy' else 'item-lease')
    remove, release = Mock(), Mock()
    process = Mock(return_value=SimpleNamespace(processing_deferred=condition == 'deferred'))
    monkeypatch.setattr(worker.store, 'claim_item', claim)
    monkeypatch.setattr(worker.store, 'remove', remove)
    monkeypatch.setattr(worker.store, 'release_item', release)
    monkeypatch.setattr(worker, 'process_conversation', process)
    result = worker._process_text('synthetic', 'capture')
    if condition in {'missing', 'deleted', 'done'}:
        assert result is worker.AttemptOutcome.COMPLETE
        remove.assert_called_once_with('synthetic', 'capture')
        claim.assert_not_called()
        release.assert_not_called()
        process.assert_not_called()
    elif condition == 'busy':
        assert result is worker.AttemptOutcome.RETRY
        process.assert_not_called()
        release.assert_not_called()
    else:
        assert result is (worker.AttemptOutcome.DEFERRED if condition == 'deferred' else worker.AttemptOutcome.COMPLETE)
        remove.assert_not_called()
        release.assert_called_once_with('synthetic', 'capture', 'item-lease')
        assert process.call_args.kwargs['trigger'] is worker.ProcessingTrigger.BACKLOG_CHOICE


@pytest.mark.parametrize(
    'exists,state,recovered,expected',
    [
        (False, 'held', False, worker.AttemptOutcome.COMPLETE),
        (True, 'purged', False, worker.AttemptOutcome.COMPLETE),
        (True, 'held', True, worker.AttemptOutcome.COMPLETE),
        (True, 'held', False, worker.AttemptOutcome.RETRY),
    ],
)
async def test_audio_attempt_adapts_recovery_boolean_without_losing_unknown_attempts(
    monkeypatch, job_harness, exists, state, recovered, expected
):
    snap = SimpleNamespace(exists=exists, to_dict=lambda: {'state': state})
    holds = Mock()
    holds.document.return_value.get.return_value = snap
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: holds)
    recover = AsyncMock(return_value=recovered)
    monkeypatch.setattr(worker.cap_hold_recovery, 'recover_selected', recover)
    result = await job_harness.real_process('synthetic', {'kind': 'audio', 'id': 'capture'})
    assert result is expected
    if not exists or state == 'purged':
        recover.assert_not_awaited()
    else:
        recover.assert_awaited_once_with('synthetic', snap)


@pytest.mark.parametrize('include_older', [False, True])
async def test_returned_deferred_releases_reservation_and_considers_older_fitting_text(
    monkeypatch, job_harness, include_older
):
    harness = job_harness
    rows = [('text', snapshot('new-deferred', started_at=20, queued_at=10, units=6))]
    if include_older:
        rows.append(('text', snapshot('older-fitting', started_at=15, queued_at=10, units=3)))
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: rows if kind == 'text' else [])
    monkeypatch.setattr(worker, '_process', harness.real_process)
    monkeypatch.setattr(worker.conversations_db, 'get_conversation', lambda uid, identity: conversation_row(identity))
    monkeypatch.setattr(worker.store, 'claim_item', lambda *args: 'item-lease')
    release, remove = Mock(), Mock()
    monkeypatch.setattr(worker.store, 'release_item', release)
    monkeypatch.setattr(worker.store, 'remove', remove)
    attempts = []

    def process(uid, language, conversation, *, trigger):
        attempts.append(conversation.id)
        return SimpleNamespace(processing_deferred=conversation.id == 'new-deferred')

    monkeypatch.setattr(worker, 'process_conversation', process)
    await worker.run('synthetic')
    expected = ['new-deferred', 'older-fitting'] if include_older else ['new-deferred']
    assert attempts == expected
    assert harness.job['state'] == 'waiting_choice' and harness.job['reserved'] == {}
    assert harness.job['remaining'] == (1 if include_older else 4)
    assert harness.job['cursor_text']['id'] == ('older-fitting' if include_older else 'new-deferred')
    assert release.call_count == len(attempts)
    remove.assert_not_called()
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]
    assert harness.scheduled == []


@pytest.mark.parametrize('remaining', [0, 10])
async def test_exhausted_actual_allowance_finishes_without_advancing_or_scanning_the_backlog(
    monkeypatch, job_harness, remaining
):
    harness = job_harness
    harness.job['remaining'] = remaining
    rows = [
        ('text', snapshot(f'capture-{index}', started_at=20 - index, queued_at=10, units=1))
        for index in range(worker.PAGE)
    ]
    page = Mock(side_effect=lambda uid, kind, cursor: rows if kind == 'text' else [])
    monkeypatch.setattr(worker, '_page', page)
    allowance = Mock(return_value=SimpleNamespace(managed=False))
    monkeypatch.setattr(worker.funded_processing, 'allowance', allowance)
    await worker.run('synthetic')
    assert harness.job['state'] == 'waiting_choice' and harness.job['remaining'] == remaining
    assert harness.job.get('cursor_text') is None and harness.job['reserved'] == {}
    assert allowance.call_count == 1 and page.call_count == 2
    assert harness.processed == [] and harness.scheduled == []
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]


@pytest.mark.parametrize('failure', ['query', 'allowance'])
async def test_unreserved_failure_consumes_pending_upgrade_and_schedules_new_token(monkeypatch, job_harness, failure):
    harness = job_harness
    harness.job['pending_upgrade'] = {'period': '2026-10', 'remaining': 100, 'cutoff': 200}
    choose = Mock(side_effect=AssertionError('Worker created new consent'))
    monkeypatch.setattr(worker, 'choose', choose)
    if failure == 'query':
        monkeypatch.setattr(worker, '_page', Mock(side_effect=RuntimeError('Query unavailable')))
    else:
        row = ('text', snapshot('capture', started_at=20, queued_at=10, units=3))
        monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [row] if kind == 'text' else [])
        monkeypatch.setattr(
            worker.funded_processing, 'allowance', Mock(side_effect=RuntimeError('Allowance unavailable'))
        )
    await worker.run('synthetic')
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-10')]
    assert harness.job['state'] == 'processing' and harness.job['token'] == 'upgrade-choice'
    assert harness.job['remaining'] == 100 and harness.job['pending_upgrade'] == {}
    assert harness.job['lease_until'] == 0 and harness.job['reserved'] == {}
    assert harness.scheduled == []  # The durable sweep owns the next token/page.
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    await worker.run('synthetic', continuation=True)
    assert harness.finishes[-1] == ('synthetic', 'upgrade-choice', 'lease', '2026-10')
    assert harness.job['state'] == 'waiting_choice'
    choose.assert_not_called()


@pytest.mark.parametrize('kind', ['text', 'audio'])
async def test_busy_text_or_unknown_audio_retry_retains_identity_and_debits_only_once(monkeypatch, job_harness, kind):
    harness = job_harness
    field = 'started_at' if kind == 'text' else 'listed_at'
    row = (kind, snapshot('capture', **{field: 20, 'queued_at': 10, 'created_at': 10, 'units': 3}))
    monkeypatch.setattr(worker, '_page', lambda uid, queue, cursor: [row] if queue == kind and not cursor else [])
    monkeypatch.setattr(worker, '_process', harness.real_process)
    if kind == 'text':
        monkeypatch.setattr(worker.conversations_db, 'get_conversation', lambda *args: conversation_row())
        monkeypatch.setattr(worker.store, 'claim_item', Mock(side_effect=[None, 'item-lease']))
        monkeypatch.setattr(worker.store, 'release_item', Mock())
        process = Mock(return_value=SimpleNamespace(processing_deferred=False))
        monkeypatch.setattr(worker, 'process_conversation', process)
    else:
        holds = Mock()
        holds.document.return_value.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'state': 'held'})
        monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: holds)
        monkeypatch.setattr(worker.cap_hold, 'remaining_seconds', lambda row: 3600)
        monkeypatch.setattr(worker, 'recording_units_per_hour', lambda mode: 3)
        process = AsyncMock(side_effect=[False, True])
        monkeypatch.setattr(worker.cap_hold_recovery, 'recover_selected', process)
    await worker.run('synthetic')
    reserved = deepcopy(harness.job['reserved'])
    assert reserved['id'] == 'capture' and reserved['kind'] == kind
    assert harness.job['state'] == 'processing' and harness.job['remaining'] == 7
    assert harness.job['lease_until'] == 0 and harness.finishes == []
    await worker.run('synthetic', continuation=True)
    assert harness.job['remaining'] == 7 and harness.job['reserved'] == {}
    assert harness.job['state'] == 'waiting_choice' and harness.scheduled == []
    assert process.call_count == (1 if kind == 'text' else 2)


@pytest.mark.parametrize('query_failure', [False, True])
async def test_finish_failure_is_logged_once_and_releases_lease(monkeypatch, job_harness, caplog, query_failure):
    harness = job_harness
    if query_failure:
        monkeypatch.setattr(worker, '_page', Mock(side_effect=RuntimeError('Query unavailable')))
    finish = Mock(side_effect=RuntimeError('Finish unavailable'))
    monkeypatch.setattr(worker.store, 'finish', finish)
    await worker.run('synthetic')
    finish.assert_called_once_with('synthetic', 'choice', 'lease', '2026-10')
    assert harness.job['lease_until'] == 0 and harness.scheduled == []
    assert 'outcome=finish_deferred exception_type=RuntimeError' in caplog.text


@pytest.mark.parametrize('raises', [False, True])
async def test_pending_upgrade_waits_for_reserved_attempt_to_have_known_outcome(monkeypatch, job_harness, raises):
    harness = job_harness
    reserved = {'kind': 'text', 'id': 'already-debited', 'units': 3}
    pending = {'period': '2026-10', 'remaining': 100, 'cutoff': 200}
    harness.job.update(reserved=deepcopy(reserved), remaining=7, pending_upgrade=deepcopy(pending))
    process = AsyncMock(return_value=worker.AttemptOutcome.RETRY)
    if raises:
        process.side_effect = RuntimeError('Uncertain application result')
    monkeypatch.setattr(worker, '_process', process)
    page = Mock(side_effect=AssertionError('Queried behind an unknown reservation'))
    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic')
    assert harness.job['reserved'] == reserved and harness.job['remaining'] == 7
    assert harness.job['pending_upgrade'] == pending and harness.job['token'] == 'choice'
    assert harness.job['lease_until'] == 0 and harness.scheduled == []
    assert len(harness.finishes) == int(raises)
    page.assert_not_called()
    process.side_effect = None
    process.return_value = worker.AttemptOutcome.COMPLETE
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    await worker.run('synthetic', continuation=True)
    assert process.await_args_list[0].args == process.await_args_list[1].args == ('synthetic', reserved)
    assert harness.job['reserved'] == {} and harness.job['pending_upgrade'] == {}
    assert harness.job['token'] == 'upgrade-choice' and harness.job['remaining'] == 100
    assert harness.scheduled == []  # The durable sweep owns the next token/page.


async def test_prior_month_job_cannot_create_consent_or_claim_a_lease(monkeypatch, job_harness):
    harness = job_harness
    harness.job['period'] = '2026-09'
    harness.job['pending_upgrade'] = {'period': '2026-09', 'remaining': 100, 'cutoff': 200}
    original = deepcopy(harness.job)
    claim = Mock(side_effect=AssertionError('Old month claimed a lease'))
    monkeypatch.setattr(worker.store, 'claim', claim)
    await worker.run('synthetic')
    claim.assert_not_called()
    assert harness.job == original and harness.finishes == [] and harness.scheduled == []


async def test_reserved_attempt_rechecks_period_after_claim_before_application(monkeypatch, job_harness):
    harness = job_harness
    harness.job.update(reserved={'kind': 'text', 'id': 'already-debited', 'units': 3}, remaining=7)
    clock = {'period': '2026-10'}
    monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: clock['period'])

    def claim(*args):
        lease = harness.claim(*args)
        clock['period'] = '2026-11'
        return lease

    monkeypatch.setattr(worker.store, 'claim', claim)
    await worker.run('synthetic')
    assert harness.processed == [] and harness.finishes == [] and harness.scheduled == []
    assert harness.job['reserved']['id'] == 'already-debited' and harness.job['remaining'] == 7
    assert harness.job['lease_until'] == 0


async def test_month_rollover_query_failure_does_not_continue_previous_month_upgrade(monkeypatch, job_harness):
    harness = job_harness
    harness.job['pending_upgrade'] = {'period': '2026-10', 'remaining': 100, 'cutoff': 200}
    clock = {'period': '2026-10'}
    monkeypatch.setattr(worker.funded_processing, 'period_id', lambda: clock['period'])

    def page(*args):
        clock['period'] = '2026-11'
        raise RuntimeError('Month rolled during query')

    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic')
    assert harness.finishes == [('synthetic', 'choice', 'lease', '2026-11')]
    assert harness.job['state'] == 'waiting_choice' and harness.job['token'] == 'choice'
    assert harness.job['remaining'] == 10 and harness.job['pending_upgrade'] == {}
    assert harness.scheduled == []


async def test_owner_visit_drains_multiple_pages_without_self_respawn(monkeypatch, job_harness):
    harness = job_harness
    harness.job['remaining'] = 100
    rows = [snapshot(str(i), started_at=100 - i, queued_at=1, units=1) for i in range(35)]

    def page(uid, kind, cursor):
        if kind == 'audio':
            return []
        offset = 0 if cursor is None else int(cursor['id']) + 1
        return [('text', snap) for snap in rows[offset : offset + worker.PAGE]]

    monkeypatch.setattr(worker, '_page', page)
    await worker.run('synthetic', max_items=100, time_budget=900)
    assert len(harness.processed) == 35
    assert harness.job['state'] == 'waiting_choice' and not harness.scheduled


async def test_monotonic_budget_stops_before_next_item_retaining_intent(monkeypatch, job_harness):
    harness = job_harness
    rows = [snapshot(str(i), started_at=90 - i, queued_at=1, units=1) for i in range(5)]
    monkeypatch.setattr(
        worker, '_page', lambda uid, kind, cursor: [('text', snap) for snap in rows] if kind == 'text' else []
    )
    now = [0.0]
    monkeypatch.setattr(worker.cap_work_budget.time, 'monotonic', lambda: now[0])

    async def process(uid, item):
        harness.processed.append(item)
        now[0] += 901
        return worker.AttemptOutcome.COMPLETE

    monkeypatch.setattr(worker, '_process', process)
    await worker.run('synthetic', max_items=100, time_budget=900)
    assert len(harness.processed) == 1
    assert harness.job['state'] == 'processing' and harness.job['reserved'] == {}
    assert harness.job['cursor_text']['id'] == '0' and not harness.finishes


async def test_prechoice_staging_remains_authorized_until_seal(monkeypatch, job_harness):
    harness = job_harness
    row = {'state': 'staging', 'created_at': 90, 'listed_at': 80, 'seconds': 1}
    snap = SimpleNamespace(id='live', to_dict=lambda: dict(row))
    monkeypatch.setattr(
        worker, '_page', lambda uid, kind, cursor: [('audio', snap)] if kind == 'audio' and not cursor else []
    )
    await worker.run('synthetic', max_items=100, time_budget=900)
    assert not harness.finishes and not harness.processed and harness.job['state'] == 'processing'
    row['state'] = 'held'  # seal retains created_at/listed_at, even after cutoff
    await worker.run('synthetic', max_items=100, time_budget=900)
    assert [p['id'] for p in harness.processed] == ['live']
    assert harness.job['state'] == 'waiting_choice'


async def test_disabled_lane_does_not_spend_estimate_or_finish_choice(job_harness, monkeypatch):
    job, processed, finishes = job_harness.job, job_harness.processed, job_harness.finishes
    row = snapshot('old-sync', listed_at=20, created_at=10, state='held', seconds=30)
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [('audio', row)] if kind == 'audio' else [])
    monkeypatch.setattr(worker, '_selected', AsyncMock(return_value=False))
    before = job['remaining']
    await worker.run('owner')
    assert job['remaining'] == before and job['reserved'] == {}
    assert job['state'] == 'processing' and len(finishes) == 1 and not processed
    assert job['cursor_audio'] is None and job['scope_skipped'] is False


async def test_skipped_lane_survives_restart_until_cursor_rewinds(job_harness, monkeypatch):
    job, processed, finishes = job_harness.job, job_harness.processed, job_harness.finishes
    job.update(scope_skipped=True, cursor_audio={'at': 20, 'id': 'excluded'})
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    await worker.run('owner')
    assert job['cursor_audio'] is None and job['scope_skipped'] is False
    assert job['state'] == 'processing' and len(finishes) == 1


@pytest.mark.parametrize('origin,selected', [('live', True), ('sync', False), ('batch', False), ('unknown', False)])
async def test_worker_selects_original_encrypted_audio_lane(monkeypatch, origin, selected):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:owner')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    ref = Mock()
    ref.document.return_value.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'metadata': 'cipher'})
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: ref)
    monkeypatch.setattr(worker.cap_hold, 'metadata', lambda uid, row: {'origin': origin})
    assert await worker._selected('owner', {'kind': 'audio', 'id': 'held'}) is selected


async def test_post_cutoff_excluded_lane_does_not_stall_chosen_work(job_harness, monkeypatch):
    job = job_harness.job
    row = snapshot('later-sync', listed_at=200, created_at=200, state='held', seconds=30)
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [('audio', row)] if kind == 'audio' else [])
    selection = AsyncMock(return_value=False)
    monkeypatch.setattr(worker, '_selected', selection)
    await worker.run('owner')
    selection.assert_not_called()
    assert job_harness.finishes and not job.get('scope_skipped')


@pytest.mark.parametrize('failure', ['lookup', 'metadata'])
async def test_unreadable_provenance_stays_paused_without_spend(monkeypatch, failure):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    ref = Mock()
    ref.document.return_value.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'metadata': 'cipher'})
    monkeypatch.setattr(worker.cap_hold, 'holds', lambda uid: ref)
    monkeypatch.setattr(worker.cap_hold, 'metadata', Mock(side_effect=OSError('synthetic storage failure')))
    if failure == 'lookup':
        ref.document.return_value.get.side_effect = OSError('synthetic manifest read failure')
    assert not await worker._selected('owner', {'kind': 'audio', 'id': 'held'})
