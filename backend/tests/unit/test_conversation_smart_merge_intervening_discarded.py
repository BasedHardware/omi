"""Intervening-discarded barrier for smart merge, end to end over the World fakes.

A discarded row of the same source and device partition whose speech interval
intersects the open gap between the survivor's ``finished_at`` and the donor's
``max(started_at, created_at)`` must refuse the fold — at decision time and
again inside the absorb transaction. The scan reuses the registered preceding
query with ``discarded=True`` and no limit, so barriers hidden beyond
``PRECEDING_QUERY_LIMIT`` still block. A verified own-constituent tombstone of
the survivor is exempt; every other discarded row, deleted or not, counts.
All text is synthetic.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Aborted
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, CommitResponse, Document, RunQueryResponse

from config import conversation_smart_merge as config
from database import smart_merge as smart_merge_db
from database.firestore_index_registry import CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient
from tests.unit.test_conversation_smart_merge import T0, UID, World
from tests.unit.test_conversation_smart_merge_wallclock import _add, _drifted_pair
from utils import metrics
from utils.conversations import smart_merge
from utils.conversations.processing_trigger import ProcessingTrigger

WALL_ENV = 'CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE'
SKIP_LINE = f'event=smart_merge decision=skip reason=intervening_discarded uid={UID} conversation=n'
INCIDENT = datetime(2026, 10, 5, 13, 6, 10, tzinfo=timezone.utc)


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(WALL_ENV, raising=False)
    return World(monkeypatch)


def _skip_lines(caplog):
    return [r.getMessage() for r in caplog.records if 'decision=skip' in r.getMessage()]


def test_incident_rows_never_fold_across_discarded_intervals(world, caplog):
    """The 2026-10-05 incident replayed at its exact wall times.

    ce79e585 started 13:06:10 and its merged span reached 13:46:05 across five
    discarded captures spanning 13:13-13:40. The test's pre-absorb split is
    synthetic: the survivor ends 13:12:00 and the fragment runs 13:42-13:46:05.
    The barrier must keep the survivor there.
    """
    hour = INCIDENT.replace(minute=0, second=0)
    world.add(
        'ce79e585',
        0,
        6,
        created_at=INCIDENT,
        started_at=INCIDENT,
        finished_at=INCIDENT + timedelta(minutes=5, seconds=50),
    )
    for index, (start_s, end_s) in enumerate(
        [(13 * 60, 16 * 60), (18 * 60, 21 * 60), (23 * 60, 26 * 60), (30 * 60, 33 * 60), (37 * 60, 40 * 60)]
    ):
        world.add(
            f'd{index}',
            0,
            3,
            discarded=True,
            created_at=hour + timedelta(seconds=start_s),
            started_at=hour + timedelta(seconds=start_s),
            finished_at=hour + timedelta(seconds=end_s),
        )
    new_created = INCIDENT + timedelta(minutes=35, seconds=50)
    world.add(
        'n',
        0,
        4,
        created_at=new_created,
        started_at=new_created,
        finished_at=INCIDENT + timedelta(minutes=39, seconds=55),
    )
    for index in range(5):
        row = world.raw(f'd{index}')
        assert hour + timedelta(minutes=13) <= row['started_at'] < row['finished_at'] <= hour + timedelta(minutes=40)
        assert row['finished_at'] < new_created
    world.jev_answers = [0.9]
    before_survivor = dict(world.raw('ce79e585'))
    caplog.set_level('INFO', logger=smart_merge.logger.name)

    assert world.finish('n') is False

    assert _skip_lines(caplog) == [SKIP_LINE]
    assert world.jev_calls == []
    donor = world.raw('n')
    assert not donor.get('deleted') and 'sync_merged_into' not in donor
    assert 'smart_merge_decision' not in donor
    assert world.raw('ce79e585') == before_survivor
    assert world.raw('ce79e585')['finished_at'] == INCIDENT + timedelta(minutes=5, seconds=50)
    assert all(len(s['text'].split()) >= 25 for s in world.transcript('n'))
    assert world.preceding_calls == [
        {'source': 'omi', 'discarded': False, 'limit': config.PRECEDING_QUERY_LIMIT, 'transaction': False},
        {'source': 'omi', 'discarded': True, 'limit': None, 'transaction': False},
    ]


def test_no_discarded_rows_still_merges(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


@pytest.mark.parametrize(
    'start_min, minutes, extra',
    [
        (-20, 5, {}),
        (50, 5, {'created_at': T0 + timedelta(minutes=14)}),
        (4, 6, {}),
        (15, 3, {}),
    ],
    ids=['before', 'after', 'touching-lower', 'touching-upper'],
)
def test_discarded_rows_outside_the_open_gap_do_not_block(world, start_min, minutes, extra):
    world.add('p', 0, 10)
    world.add('d', start_min, minutes, discarded=True, **extra)
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


@pytest.mark.parametrize(
    'extra, path_uid',
    [
        ({'client_device_id': 'pendant-2'}, UID),
        ({'source': 'sd'}, UID),
        ({}, 'other-user'),
    ],
    ids=['other-device', 'other-source', 'other-uid'],
)
def test_discarded_rows_of_other_partitions_do_not_block(world, extra, path_uid):
    world.add('p', 0, 10)
    world.add('d', 11, 2, discarded=True, **extra)
    if path_uid != UID:
        row = world.store.rows.pop(('users', UID, 'conversations', 'd'))
        world.store.rows[('users', path_uid, 'conversations', 'd')] = row
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


def test_barriers_beyond_the_preceding_limit_still_block(world):
    """The true-discard scan is unbounded: newer out-of-gap or foreign-device
    rows must not push a real barrier past ``PRECEDING_QUERY_LIMIT``."""
    world.add('p', 0, 10)
    world.add('d', 12, 1, discarded=True)
    for index in range(config.PRECEDING_QUERY_LIMIT + 2):
        world.add(f'noise-{index}', 13 + index, 1, discarded=True, client_device_id='pendant-2')
    world.add('n', 40, 5)
    world.jev_answers = [0.9]
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted')


@pytest.mark.parametrize('delay_minutes', [0, 5, 20], ids=['equal', 'plus-five', 'much-later'])
def test_delayed_creation_discard_still_blocks(world, caplog, delay_minutes):
    """Ingestion delay is not a hiding place: a discarded capture whose
    ``created_at`` landed at or after the donor's ``created_at`` still occupies
    the gap — the barrier scan must not cut at the donor's creation time."""
    world.add('p', 0, 10)
    donor_created = T0 + timedelta(minutes=15)
    world.add('d', 11, 2, discarded=True, created_at=donor_created + timedelta(minutes=delay_minutes))
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    assert world.finish('n') is False
    assert _skip_lines(caplog) == [SKIP_LINE]
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted')
    assert world.preceding_calls[-1] == {
        'source': 'omi',
        'discarded': True,
        'limit': None,
        'transaction': False,
    }


@pytest.mark.parametrize(
    'tomb_extra, lineage',
    [
        ({'smart_merge': None}, ['p', 'd']),
        ({'smart_merge': {'role': 'donor', 'survivor_id': 'q'}}, ['p', 'd']),
        ({'deleted': False}, ['p', 'd']),
        ({}, ['p']),
    ],
    ids=['marker-only', 'redirect-other-survivor', 'not-deleted', 'fake-lineage'],
)
def test_tombstone_claims_without_full_lineage_still_block(world, caplog, tomb_extra, lineage):
    """Only a verified own constituent is exempt: the redirect marker, the
    donor ledger entry and membership in the survivor's lineage must all hold;
    each alone still blocks."""
    world.add('p', 0, 10)
    world.raw('p')['sync_merged_from'] = list(lineage)
    world.raw('p')['smart_merge'] = {'role': 'survivor', 'fragments': [{'id': fid} for fid in lineage]}
    tomb = {'deleted': True, 'sync_merged_into': 'p', 'smart_merge': {'role': 'donor', 'survivor_id': 'p'}}
    tomb.update(tomb_extra)
    if tomb['smart_merge'] is None:
        del tomb['smart_merge']
    world.add('d', 11, 2, discarded=True, **tomb)
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    assert world.finish('n') is False
    assert _skip_lines(caplog) == [SKIP_LINE]
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted')


@pytest.mark.parametrize('wall_mode', ['off', 'shadow', 'on'])
def test_drifted_same_recording_pair_with_barrier_never_merges(world, caplog, wall_mode):
    """p finished 600 s, n created 720 s / started 400 s / finished 1020 s,
    discarder 650-680 s. Under ``on`` the wall-clock rescue would otherwise
    admit the pair; the barrier must win in every mode."""
    _drifted_pair(world)
    _add(world, 'd', 640, 650, 680, discarded=True)
    world.jev_answers = [0.9]
    world.monkeypatch.setenv(WALL_ENV, wall_mode)
    caplog.set_level('INFO', logger=smart_merge.logger.name)

    assert world.finish('n') is False

    assert _skip_lines(caplog) == [SKIP_LINE]
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted')
    assert 'smart_merge_decision' not in world.raw('n')


def test_shadow_pair_with_barrier_records_nothing(world):
    world.add('p', 0, 10)
    world.add('d', 11, 2, discarded=True)
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    assert world.finish('n', mode='shadow') is False
    assert world.jev_calls == [] and 'smart_merge_decision' not in world.raw('n')


def test_discard_written_between_decide_and_absorb_rejects_in_transaction(world, caplog):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.9]
    world.monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'merge')
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None and plan.survivor_id == 'p'

    world.add('d', 11, 2, discarded=True)
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is False

    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'intervening_discarded'
    assert _skip_lines(caplog) == [SKIP_LINE]
    assert not world.raw('n').get('deleted') and 'smart_merge' not in world.raw('p')
    assert [s['id'] for s in world.transcript('p')] == ['p-s0', 'p-s1']
    assert {'source': 'omi', 'discarded': True, 'limit': None, 'transaction': True} in world.preceding_calls


def test_row_flipping_discarded_between_decide_and_absorb_rejects(world):
    """A locked row is a foreign partition while visible; once discarded it
    still blocks — the barrier filter is device only, never is_locked."""
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.add('d', 11, 2, is_locked=True)
    world.jev_answers = [0.9]
    world.monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'merge')
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None and plan.survivor_id == 'p'

    world.raw('d')['discarded'] = True
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is False

    assert world.raw('n')['smart_merge_decision']['reason'] == 'intervening_discarded'
    assert not world.raw('n').get('deleted')
    assert {'source': 'omi', 'discarded': True, 'limit': None, 'transaction': True} in world.preceding_calls


def test_intervening_discarded_keeps_its_own_metric_reason(world):
    world.add('p', 0, 10)
    world.add('d', 11, 2, discarded=True)
    world.add('n', 15, 10)
    seen = []
    world.monkeypatch.setattr(
        metrics.CONVERSATION_SMART_MERGE_DECISION_TOTAL,
        'labels',
        lambda **labels: SimpleNamespace(inc=lambda: seen.append(labels)),
    )
    assert world.finish('n') is False
    assert seen == [{'mode': 'merge', 'decision': 'skip', 'reason': 'intervening_discarded', 'gap_bucket': 'none'}]


def test_invalid_endpoints_fall_through_to_the_existing_gates(world):
    survivor = {'id': 'p', 'finished_at': 'not-a-datetime'}
    donor = {'id': 'n', 'source': 'omi', 'started_at': T0, 'created_at': T0}
    assert smart_merge_db.has_intervening_discarded(UID, survivor, donor) is False
    donor['started_at'] = 12.5
    assert smart_merge_db.has_intervening_discarded(UID, {'finished_at': T0}, donor) is False


def _field_filters(request, client):
    """Decode a captured RunQuery request's composite field filters."""
    where = request['structured_query'].where
    out = []
    for entry in where.composite_filter.filters:
        field_filter = entry.field_filter
        out.append(
            (
                field_filter.field.field_path,
                field_filter.op.name,
                _helpers.decode_value(field_filter.value, client),
            )
        )
    return out


def _project(row, field_paths):
    if not field_paths:
        return dict(row)
    out = {}
    for field_path in field_paths:
        parts = field_path.split('.')
        src, dst = row, out
        for index, part in enumerate(parts):
            if not isinstance(src, dict) or part not in src:
                break
            if index == len(parts) - 1:
                dst[part] = src[part]
            else:
                dst = dst.setdefault(part, {})
                src = src[part]
    return out


@pytest.fixture
def sdk_world(monkeypatch):
    """Real SDK client over mocked RPCs; the production query functions run unpatched."""
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(WALL_ENV, raising=False)
    real_preceding = smart_merge_db.find_preceding_conversations
    world = World(monkeypatch)
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    monkeypatch.setattr(smart_merge_db, 'find_preceding_conversations', real_preceding)
    client = OfflineFirestoreClient(project='synthetic-intervening-test')
    api = MagicMock()
    client._firestore_api_internal = api
    monkeypatch.setattr(smart_merge_db, 'get_firestore_client', lambda: client)
    committed, rollbacks, queries = [], [], []
    state = SimpleNamespace(compete=None, aborted=False)

    def begin(**kwargs):
        return SimpleNamespace(transaction=f'txn-{api.begin_transaction.call_count}'.encode())

    def batch_get(*, request, **kwargs):
        out = []
        for name in request['documents']:
            path = tuple(name.split('/documents/', 1)[1].split('/'))
            row = world.store.rows.get(path)
            out.append(
                BatchGetDocumentsResponse(missing=name)
                if row is None
                else BatchGetDocumentsResponse(found=Document(name=name, fields=_helpers.encode_dict(row)))
            )
        return iter(out)

    def run_query(*, request, **kwargs):
        queries.append(request)
        structured = request['structured_query']
        filters = dict()
        for path, op, value in _field_filters(request, client):
            filters.setdefault(path, []).append((op, value))
        discarded = next((value for op, value in filters.get('discarded', []) if op == 'EQUAL'), None)
        source = next((value for op, value in filters.get('source', []) if op == 'EQUAL'), None)
        statuses = next((value for op, value in filters.get('status', []) if op == 'IN'), None)
        created_before = next((value for op, value in filters.get('created_at', []) if op == 'LESS_THAN'), None)
        docs = []
        for path, row in world.store.rows.items():
            if path[:3] != ('users', UID, 'conversations'):
                continue
            if discarded is not None and row.get('discarded') is not discarded:
                continue
            if source is not None and row.get('source') != source:
                continue
            if statuses is not None and row.get('status') not in statuses:
                continue
            if created_before is not None and not row['created_at'] < created_before:
                continue
            docs.append((path, row))
        order = structured.order_by[0] if structured.order_by else None
        reverse = order is not None and order.direction.name == 'DESCENDING'
        order_path = order.field.field_path if order is not None else 'created_at'
        docs.sort(key=lambda item: item[1][order_path], reverse=reverse)
        if 'limit' in structured:
            docs = docs[: structured.limit]
        field_paths = [field.field_path for field in structured.select.fields]
        return iter(
            RunQueryResponse(
                document=Document(
                    name=f"{client._database_string}/documents/{'/'.join(path)}",
                    fields=_helpers.encode_dict(_project(row, field_paths)),
                )
            )
            for path, row in docs
        )

    def commit(*, request, **kwargs):
        abort_on = any(
            write.update.name.endswith('/conversations/n') and 'deleted' in write.update.fields
            for write in request['writes']
        )
        if state.compete is not None and abort_on and not state.aborted:
            state.aborted = True
            state.compete()
            raise Aborted('synthetic conflict before commit')
        committed.append(request)
        for write in request['writes']:
            path = tuple(write.update.name.split('/documents/', 1)[1].split('/'))
            data = _helpers.decode_dict(write.update.fields, client)
            if write.update_mask.field_paths:
                world.store.rows.setdefault(path, {}).update(data)
            else:
                world.store.rows[path] = data
        return CommitResponse(commit_time=datetime.now(timezone.utc))

    api.begin_transaction.side_effect = begin
    api.batch_get_documents.side_effect = batch_get
    api.run_query.side_effect = run_query
    api.commit.side_effect = commit
    api.rollback.side_effect = lambda *, request, **kw: rollbacks.append(request['transaction'])
    return SimpleNamespace(world=world, client=client, api=api, state=state, committed=committed, queries=queries)


def test_discarded_scan_request_uses_the_registered_shape(sdk_world):
    test = sdk_world
    rows = smart_merge_db.find_preceding_conversations(
        UID,
        source='omi',
        created_before=T0 + timedelta(minutes=16),
        limit=None,
        discarded=True,
        firestore_client=test.client,
    )
    assert rows == []
    request = test.queries[-1]
    fields = _field_filters(request, test.client)
    assert ('discarded', 'EQUAL', True) in fields
    assert ('source', 'EQUAL', 'omi') in fields
    assert ('status', 'IN', list(smart_merge_db._ALL_STATUSES)) in fields
    assert ('created_at', 'LESS_THAN', T0 + timedelta(minutes=16)) in fields
    orders = [entry.field.field_path for entry in request['structured_query'].order_by]
    assert orders == ['created_at']
    assert 'limit' not in request['structured_query']
    assert not request.get('transaction')
    projected = [field.field_path for field in request['structured_query'].select.fields]
    assert 'transcript_segments' not in projected
    for needed in ('deleted', 'sync_merged_into', 'smart_merge', 'client_device_id', 'started_at', 'finished_at'):
        assert needed in projected
    index_fields = [field.field_path for field in CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY.index_fields]
    assert index_fields[:4] == ['discarded', 'source', 'status', 'created_at']


def test_barrier_scan_uses_the_max_created_bound(sdk_world):
    """The helper's own call sends ``created_at < datetime.max``: every
    representable creation time is in scope, so no created_at alignment with
    speech times can hide a barrier."""
    test = sdk_world
    survivor = {'id': 'p', 'finished_at': T0 + timedelta(minutes=10)}
    donor = {
        'id': 'n',
        'source': 'omi',
        'client_device_id': 'pendant-1',
        'started_at': T0 + timedelta(minutes=15),
        'created_at': T0 + timedelta(minutes=15),
    }
    smart_merge_db.has_intervening_discarded(UID, survivor, donor, firestore_client=test.client)
    request = test.queries[-1]
    fields = _field_filters(request, test.client)
    assert ('discarded', 'EQUAL', True) in fields
    assert ('source', 'EQUAL', 'omi') in fields
    assert ('status', 'IN', list(smart_merge_db._ALL_STATUSES)) in fields
    assert ('created_at', 'LESS_THAN', datetime.max.replace(tzinfo=timezone.utc)) in fields
    orders = [entry.field.field_path for entry in request['structured_query'].order_by]
    assert orders == ['created_at']
    assert 'limit' not in request['structured_query']


def test_bounded_scan_applies_the_request_limit(sdk_world):
    test = sdk_world
    world = test.world
    world.add('a', 12, 1)
    world.add('b', 13, 1)
    rows = smart_merge_db.find_preceding_conversations(
        UID,
        source='omi',
        created_before=T0 + timedelta(minutes=16),
        limit=1,
        firestore_client=test.client,
    )
    assert [row['id'] for row in rows] == ['n']
    request = test.queries[-1]
    assert request['structured_query'].limit == 1


def test_own_constituent_tombstone_is_exempt_under_the_real_projection(sdk_world):
    """The exempted path runs through the real projected select: a deleted
    donor tombstone ledgered into this survivor and listed in its lineage is
    the survivor's own constituent; a marker redirecting elsewhere blocks."""
    test = sdk_world
    tomb = {
        'deleted': True,
        'sync_merged_into': 'p',
        'smart_merge': {'role': 'donor', 'survivor_id': 'p'},
    }
    test.world.add('d', 11, 4, discarded=True, **tomb)
    survivor = {
        'id': 'p',
        'finished_at': T0 + timedelta(minutes=10),
        'sync_merged_from': ['d'],
        'smart_merge': {'role': 'survivor', 'fragments': [{'id': 'p'}, {'id': 'd'}]},
    }
    donor = {
        'id': 'n',
        'source': 'omi',
        'client_device_id': 'pendant-1',
        'started_at': T0 + timedelta(minutes=15),
        'created_at': T0 + timedelta(minutes=15),
    }
    assert smart_merge_db.has_intervening_discarded(UID, survivor, donor, firestore_client=test.client) is False
    test.world.raw('d')['smart_merge'] = {'role': 'donor', 'survivor_id': 'q'}
    assert smart_merge_db.has_intervening_discarded(UID, survivor, donor, firestore_client=test.client) is True


def test_barrier_seen_only_on_retry_rejects_inside_the_absorb_transaction(sdk_world):
    """A discarded row committed between decide and commit aborts the absorb.

    The first attempt's scan sees no barrier; a competing transaction writes it
    before the commit Aborts, and the SDK retry's transaction-bound scan sees
    the barrier and rejects instead of folding across it."""
    test = sdk_world
    world = test.world
    world.jev_answers = [0.9]
    world.monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'merge')

    def write_barrier():
        world.add('d', 11, 2, discarded=True, created_at=world.raw('n')['created_at'] + timedelta(minutes=5))

    test.state.compete = write_barrier

    assert world.finish('n') is False
    assert test.state.aborted
    assert test.api.begin_transaction.call_count >= 2
    donor = world.raw('n')
    assert not donor.get('deleted') and 'sync_merged_into' not in donor
    assert donor['smart_merge_decision']['reason'] == 'intervening_discarded'
    committed = [write for request in test.committed for write in request['writes']]
    assert not any('deleted' in write.update.fields for write in committed)
    transactional_scans = [q for q in test.queries if q.get('transaction')]
    assert transactional_scans, 'the barrier scan must run inside the transaction'
    for request in transactional_scans:
        assert isinstance(request['transaction'], bytes) and request['transaction']
        assert ('discarded', 'EQUAL', True) in _field_filters(request, test.client)
