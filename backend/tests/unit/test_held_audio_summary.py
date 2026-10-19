import asyncio
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from models.users import HeldAudioSummary
from database import processing_backlog as backlog_store
from database import fsr_read_cache
from database.fsr_read_cache import forget_request_reads, request_read_scope
from utils import processing_backlog as backlog, processing_backlog_worker as backlog_worker
from utils.sync import cap_hold, cap_hold_recovery
from utils.sync import held_audio_summary as summary


def test_manifest_records_recording_start():
    body = cap_hold.hold_manifest({'audio_path': 'chunks/u/cap-held/a.wav.enc'}, 12.4, 100.0, 1_700_000_000)
    assert body['started_at'] == 1_700_000_000
    assert body['listed_at'] == 1_700_000_000
    assert body['state'] == 'held'
    assert body['seconds'] == 12.4
    assert cap_hold.hold_started_at({'timestamp': 12.9}) == 12
    assert cap_hold.hold_started_at({'timestamp': True}) is None
    assert cap_hold.hold_started_at({}) is None


def test_flag_off_does_not_read_holds(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')

    def explode(uid):
        raise AssertionError('holds were read while dispatch enforcement is off')

    monkeypatch.setattr(summary, '_load_rows', explode)
    monkeypatch.setattr(summary, '_load_summary', explode)
    monkeypatch.setattr(summary, 'funded_allowance', explode)
    assert summary.client_held_audio('synthetic') is None


def test_exhausted_account_lists_holds_and_asks_the_client_to_retain_live(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=False),
        rows=[
            {'id': 'older', 'started_at': 100, 'seconds': 30},
            {'id': 'newer', 'started_at': 200, 'seconds': 90},
            {'id': 'empty', 'started_at': 300, 'seconds': 0},
        ],
        now=now,
    )
    assert isinstance(result, HeldAudioSummary)
    assert result.retain_live is True
    assert result.seconds == 120
    assert result.count == 2
    assert [row.id for row in result.recordings] == ['newer', 'older']
    assert result.reset_at == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())


def test_funded_account_with_nothing_held_omits_the_field(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True), rows=[]) is None


def test_funded_account_still_reports_audio_already_held(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=True),
        rows=[{'id': 'held', 'started_at': 50, 'seconds': 15}],
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result is not None
    assert result.retain_live is False
    assert result.seconds == 15
    assert result.count == 1


def test_summary_total_is_exact_when_the_page_is_truncated(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=False),
        summary={'seconds': 9000, 'count': 40},
        rows=[{'id': 'newest', 'started_at': 500, 'seconds': 30}],
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result is not None
    assert result.seconds == 9000
    assert result.count == 40
    assert [row.id for row in result.recordings] == ['newest']


def test_positive_count_reads_the_summary_then_one_page(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    reads = {'summary': 0, 'rows': 0}

    def load_summary(uid):
        reads['summary'] += 1
        return {'seconds': 40, 'count': 2}

    def load_rows(uid):
        reads['rows'] += 1
        return [{'id': 'a', 'started_at': 2, 'seconds': 10}, {'id': 'b', 'started_at': 1, 'seconds': 30}]

    def explode(*args, **kwargs):
        raise AssertionError('funded_allowance was resolved again')

    monkeypatch.setattr(summary, '_load_summary', load_summary)
    monkeypatch.setattr(summary, '_load_rows', load_rows)
    monkeypatch.setattr(summary, 'funded_allowance', explode)
    result = summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=False))
    assert reads == {'summary': 1, 'rows': 1}
    assert result is not None and result.seconds == 40 and result.count == 2


def test_empty_summary_does_not_query_holds(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(summary, '_load_summary', lambda uid: {'seconds': 0, 'count': 0})
    monkeypatch.setattr(summary, '_load_rows', lambda uid: (_ for _ in ()).throw(AssertionError('page was read')))
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True)) is None


def test_plus_anniversary_is_not_the_minute_counter_reset():
    """Legacy Plus billing can end mid-month. The counter still rolls at 00:00 UTC on the 1st."""
    plus = SimpleNamespace(plan='plus', current_period_end=int(datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp()))
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert summary.plan_reset_at(plus, now) == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())


def test_subscription_open_never_creates_recovery_intent(monkeypatch):
    choose = Mock(side_effect=AssertionError('subscription read created processing consent'))
    start = Mock(side_effect=AssertionError('subscription read persisted processing intent'))
    run = AsyncMock(side_effect=AssertionError('subscription read started paid work'))
    recover = AsyncMock(side_effect=AssertionError('subscription read started held recovery'))
    monkeypatch.setattr(backlog, 'choose', choose)
    monkeypatch.setattr(backlog_store, 'start', start)
    monkeypatch.setattr(backlog_worker, 'run', run)
    monkeypatch.setattr(cap_hold_recovery, 'recover', recover)
    for managed in (False, True):
        monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
        monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
        response = SimpleNamespace()
        allowance = SimpleNamespace(managed=managed)
        summary.attach_subscription_held_audio(response, 'synthetic', allowance)
        assert not hasattr(response, 'held_audio') or response.held_audio is None

        monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
        monkeypatch.setattr(summary, '_load_summary', lambda uid: {'seconds': 5, 'count': 1})
        monkeypatch.setattr(summary, '_load_rows', lambda uid: [{'id': 'a', 'started_at': 9, 'seconds': 5}])
        summary.attach_subscription_held_audio(response, 'synthetic', allowance)
        assert response.held_audio.seconds == 5
        for entry in (choose, start, run, recover):
            entry.assert_not_called()


def test_partial_receipts_and_retries_adjust_summary_under_lease(monkeypatch):
    from contextlib import nullcontext
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    key = ('users', 'synthetic', 'stt_cap_holds', 'a')
    total_key = ('users', 'synthetic', 'stt_cap_hold_summary', 'current')
    client = StrictFirestore(
        {
            key: {'state': 'held', 'lease_until': 1000, 'lease_token': 'owner', 'seconds': 80},
            total_key: {'version': 2, 'seconds': 80, 'count': 1},
        }
    )
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda uid: nullcontext())
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 100)
    ref = client.document('/'.join(key))
    # VAD planned only 60s; discarded silence ceases to be waiting.
    assert cap_hold.checkpoint('synthetic', ref, 'owner', {'piece_plan': {'a': {'seconds': 20}, 'b': {'seconds': 40}}})
    assert client.rows[total_key]['seconds'] == 60
    for _ in range(2):
        assert cap_hold.checkpoint('synthetic', ref, 'owner', {'piece_receipts': {'a': {'state': 'transcribed'}}})
        assert client.rows[total_key]['seconds'] == 40
    assert not cap_hold.checkpoint('synthetic', ref, 'stale', {'state': 'completed'})
    assert cap_hold.checkpoint(
        'synthetic',
        ref,
        'owner',
        {
            'piece_receipts': {'a': {'state': 'transcribed'}, 'b': {'state': 'failed_reconciliation'}},
            'failed_reconciliation': True,
            'state': 'completed',
        },
    )
    assert client.rows[total_key] == {'version': 2, 'seconds': 40, 'count': 1}
    assert cap_hold.checkpoint('synthetic', ref, 'owner', {'state': 'retained'})
    assert client.rows[total_key]['seconds'] == 40


def test_fractional_pieces_do_not_accumulate_rounding_drift(monkeypatch):
    assert cap_hold.summary_after({'seconds': 0.4, 'count': 1}, 0.4, 1)['seconds'] == 0.8
    assert cap_hold.remaining_seconds({'state': 'held', 'piece_plan': {}, 'seconds': 80}) == 0


class _HoldQuery:
    def __init__(self, events):
        self.events = events

    def where(self, *args, **kwargs):
        self.events.append('where')
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.events.append(('limit', count))
        return self

    def stream(self):
        self.events.append('stream')
        return []


def _summary_ref(payload):
    return lambda uid: SimpleNamespace(
        get=lambda: SimpleNamespace(exists=True, to_dict=lambda: dict(payload)),
    )


def test_zero_summary_count_issues_no_hold_list_read(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    events = []
    monkeypatch.setattr(summary, 'holds', lambda uid: _HoldQuery(events))
    monkeypatch.setattr(cap_hold, 'summary_ref', _summary_ref({'version': 2, 'seconds': 0, 'count': 0}))
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True)) is None
    retained = summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=False))
    assert retained is not None and retained.count == 0 and retained.recordings == []
    assert events == []


def test_positive_summary_count_lists_at_most_twenty_holds(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    events = []
    monkeypatch.setattr(summary, 'holds', lambda uid: _HoldQuery(events))
    monkeypatch.setattr(cap_hold, 'summary_ref', _summary_ref({'version': 2, 'seconds': 30, 'count': 2}))
    result = summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=False))
    assert result is not None and result.count == 2
    assert events == ['where', ('limit', summary.LIST_LIMIT), 'stream']


def test_summary_documents_dedupe_inside_one_request_and_name_their_callers(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"request_read_dedupe":100}')
    callers = []
    gets = {'held': 0, 'deferred': 0}

    class HeldRef:
        def get(self):
            frame = inspect.currentframe().f_back
            callers.append(f"{frame.f_globals['__name__']}:{frame.f_code.co_name}")
            gets['held'] += 1
            return SimpleNamespace(exists=True, to_dict=lambda: {'version': 2, 'seconds': 0, 'count': 0})

    class DeferredRef:
        def get(self):
            frame = inspect.currentframe().f_back
            callers.append(f"{frame.f_globals['__name__']}:{frame.f_code.co_name}")
            gets['deferred'] += 1
            return SimpleNamespace(exists=True, to_dict=lambda: {'count': 0})

    monkeypatch.setattr(cap_hold, 'summary_ref', lambda uid: HeldRef())
    monkeypatch.setattr(backlog_store, 'summary_ref', lambda uid: DeferredRef())

    async def once():
        scope = request_read_scope()
        await anext(scope)
        try:
            assert cap_hold.ensure_summary('synthetic')['count'] == 0
            assert cap_hold.ensure_summary('synthetic')['count'] == 0
            assert backlog_store.read('synthetic') == {'count': 0}
            assert backlog_store.read('synthetic') == {'count': 0}
            forget_request_reads('synthetic')
            assert cap_hold.ensure_summary('synthetic')['count'] == 0
            assert backlog_store.read('synthetic') == {'count': 0}
        finally:
            await scope.aclose()

    asyncio.run(once())
    assert gets == {'held': 2, 'deferred': 2}
    assert callers == [
        'utils.sync.cap_hold:read_held_audio_summary',
        'database.processing_backlog:read_processing_backlog_summary',
        'utils.sync.cap_hold:read_held_audio_summary',
        'database.processing_backlog:read_processing_backlog_summary',
    ]


def test_summary_documents_reread_when_request_dedupe_is_off(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    gets = {'held': 0}

    class HeldRef:
        def get(self):
            gets['held'] += 1
            return SimpleNamespace(exists=True, to_dict=lambda: {'version': 2, 'seconds': 0, 'count': 0})

    monkeypatch.setattr(cap_hold, 'summary_ref', lambda uid: HeldRef())

    async def once():
        scope = request_read_scope()
        await anext(scope)
        try:
            cap_hold.ensure_summary('synthetic')
            cap_hold.ensure_summary('synthetic')
        finally:
            await scope.aclose()

    asyncio.run(once())
    assert gets['held'] == 2


def test_summary_memo_is_dropped_only_after_the_staged_write_commits(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"request_read_dedupe":100}')
    gets = {'n': 0}
    order = []

    class SummaryRef:
        def get(self):
            gets['n'] += 1
            return SimpleNamespace(exists=True, to_dict=lambda: {'count': 1, 'seconds': 1, 'units': 1})

    class ItemRef:
        def get(self, transaction=None):
            return SimpleNamespace(to_dict=lambda: {'seconds': 1, 'units': 1, 'queued_at': 1, 'started_at': 0})

    class Items:
        def document(self, identity):
            return ItemRef()

    class Tx:
        def set(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

    class Fence:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(backlog_store, 'summary_ref', lambda uid, firestore_client=None: SummaryRef())
    monkeypatch.setattr(backlog_store, 'items', lambda uid, firestore_client=None: Items())

    def tracking_forget(uid):
        order.append('forget')
        forget_request_reads(uid)

    monkeypatch.setattr(fsr_read_cache, 'forget_request_reads', tracking_forget)

    async def once():
        scope = request_read_scope()
        await anext(scope)
        try:
            assert backlog_store.read('synthetic')['count'] == 1
            staged = backlog_store.stage_transition(
                Tx(),
                'synthetic',
                'text',
                {},
                {'processing_deferred': False},
                firestore_client=object(),
            )
            assert staged is True
            assert order == []
            assert backlog_store.read('synthetic')['count'] == 1
            assert gets['n'] == 1

            def fake_transactional(fn):
                def wrapped(tx):
                    order.append('begin')
                    result = fn(tx)
                    order.append('end')
                    return result

                return wrapped

            monkeypatch.setattr(backlog_store.firestore, 'transactional', fake_transactional)
            monkeypatch.setattr(
                backlog_store, 'get_firestore_client', lambda: SimpleNamespace(transaction=lambda: Tx())
            )
            monkeypatch.setattr(backlog_store, 'external_write_fence', lambda uid, *, firestore_client: Fence())
            backlog_store.remove('synthetic', 'text')
            assert order == ['begin', 'end', 'forget']
            assert backlog_store.read('synthetic')['count'] == 1
            assert gets['n'] == 2
        finally:
            await scope.aclose()

    asyncio.run(once())


def test_held_summary_is_present_with_legacy_dispatch_alone(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    result = summary.client_held_audio(
        'synthetic', allowance=SimpleNamespace(managed=False), rows=[{'id': 'held', 'started_at': 100, 'seconds': 60}]
    )
    assert result.seconds == 60 and result.retain_live is True
