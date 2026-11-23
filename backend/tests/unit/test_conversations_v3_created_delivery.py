"""Conversation-created delivery for v3-derived rows: armed once, delivered once, never for hidden work."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from database import conversations_v3 as store, conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from utils.app_integrations import ExternalIntegrationFanoutError
from utils.conversations.v3 import created, processing, service
from tests.unit.test_conversations_v3_review import AT, builder, source  # noqa: F401
from tests.unit.test_conversations_v3_transactions import strict  # noqa: F401

C = ('users', 'synthetic', 'conversations', 'c')


def derived(**updates):
    return {
        'id': 'c',
        'v3_derived': True,
        'status': 'completed',
        'home_hidden': False,
        'sync_content_revision': 1,
        'transcript_segments': [{'text': 'a real conversation about the plan'}],
        'structured': {'title': 'Plan'},
        **updates,
    }


def settle(strict, *, notes=True):
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    armed = writers.settle_processing('synthetic', 'c', token, 1, AT, notes=notes, firestore_client=strict)
    leases.release('synthetic', 'summary-c', token, firestore_client=strict)
    return armed


@pytest.fixture
def delivery(strict, monkeypatch):
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(created, 'run_blocking', blocking)
    monkeypatch.setattr(
        writers,
        'pending_created',
        lambda uid: [
            key[-1] for key, row in strict.rows.items() if key[2] == 'conversations' and row.get('v3_created_pending')
        ],
    )
    monkeypatch.setattr(created.conversations_db, 'get_conversation', lambda uid, cid: dict(strict.rows[C]))
    monkeypatch.setattr(created, 'deserialize_conversation', lambda data: SimpleNamespace(id=data['id']))
    sent, wakes, failures = [], [], []

    async def trigger(uid, conversation, **kwargs):
        if failures:
            raise failures.pop(0)
        sent.append((uid, conversation.id, kwargs))
        return []

    monkeypatch.setattr(created, 'trigger_external_integrations', trigger)
    monkeypatch.setattr(created, 'enqueue', lambda uid, at=None: wakes.append(at))
    return SimpleNamespace(sent=sent, wakes=wakes, failures=failures)


def test_notes_settle_arms_one_delivery_for_a_visible_completed_row(strict):
    strict.rows[C] = derived()
    assert settle(strict) is True
    assert strict.rows[C]['v3_created_pending'] is True and strict.rows[C]['v3_notes_written'] is True


@pytest.mark.parametrize(
    'updates',
    [
        {'home_hidden': True},
        {'terminal_no_derived_effects': True},
        {'backfilled': True},
        {'is_locked': True},
        {'discarded': True},
        {'recording': True},
        {'status': 'processing'},
        {'v3_created_delivered_at': AT},
        {'data_protection_level': 'private'},
    ],
)
def test_notes_settle_never_arms_hidden_suppressed_or_delivered_rows(strict, updates):
    strict.rows[C] = derived(**updates)
    assert settle(strict) is False
    assert 'v3_created_pending' not in strict.rows[C]


def test_short_path_settle_writes_no_notes_and_owes_nothing(strict):
    strict.rows[C] = derived()
    assert settle(strict, notes=False) is False
    assert 'v3_notes_written' not in strict.rows[C] and 'v3_created_pending' not in strict.rows[C]


def test_completed_word_floor_is_observed_once_on_settlement(strict, monkeypatch):
    strict.rows[C] = derived(v3_process_pending=True)
    observe = Mock()
    monkeypatch.setattr(writers.metrics, 'observe_word_floor', observe)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    for _ in range(2):
        writers.settle_processing(
            'synthetic', 'c', token, 1, AT, word_floor_outcomes=(True, False), firestore_client=strict
        )
    observe.assert_called_once_with(True, False)


@pytest.mark.parametrize(
    'updates,outcome',
    [
        ({}, 'visible'),
        ({'home_hidden': True}, 'hidden'),
        ({'discarded': True}, None),
        ({'deleted': True}, None),
        ({'backfilled': True}, None),
        ({'status': 'failed'}, None),
        ({'manual_end': False}, None),
    ],
)
def test_manual_end_visibility_counts_successful_settlements(strict, monkeypatch, updates, outcome):
    row = derived(manual_end=True, v3_process_pending=True)
    strict.rows[C] = {**row, **updates}
    counter = Mock()
    monkeypatch.setattr(writers.metrics, 'MANUAL_END_HOME', counter)
    settle(strict, notes=False)
    settle(strict, notes=False)  # No additional settlement is owed here.
    if outcome is None:
        counter.labels.assert_not_called()
    else:
        counter.labels.assert_called_once_with(outcome)
        counter.labels.return_value.inc.assert_called_once_with()


@pytest.mark.parametrize(
    'counter,label_keys,outcomes',
    [
        (
            writers.metrics.WORD_FLOOR_COMPLETIONS,
            ('method', 'floor'),
            {('legacy', 'below'), ('legacy', 'met'), ('script_aware', 'below'), ('script_aware', 'met')},
        ),
        (writers.metrics.MANUAL_END_HOME, ('visibility',), {('visible',), ('hidden',)}),
    ],
)
def test_cloud_run_sync_scrapes_v3_processing_outcomes(counter, label_keys, outcomes):
    profile = Path(__file__).resolve().parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml'
    rules = yaml.safe_load(profile.read_text())['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    samples = [sample for family in counter.collect() for sample in family.samples if sample.name.endswith('_total')]
    assert {tuple(s.labels[key] for key in label_keys) for s in samples} == outcomes
    assert all(re.fullmatch(rule['regex'], sample.name) for sample in samples)


def test_discovery_skips_parked_deliveries_without_hiding_python_work(monkeypatch):
    def snapshot(cid, engine):
        return SimpleNamespace(id=cid, to_dict=lambda: {'finalization_engine': engine, 'finalization_owner_epoch': 1})

    pending = snapshot('a', 'pending')
    go = snapshot('b', 'go')
    python = SimpleNamespace(id='c', to_dict=lambda: {})
    monkeypatch.setattr(writers, 'CREATED_PAGE', 2)
    collection = Mock()
    query = collection.where.return_value
    query.limit.return_value.stream.return_value = [pending, go]
    query.start_after.return_value.limit.return_value.stream.return_value = [python]
    monkeypatch.setattr(store, 'user_conversations', lambda *_: collection)

    assert writers.pending_created('synthetic', firestore_client=object()) == ['c']
    query.start_after.assert_called_once_with(go)

    query.reset_mock()
    query.limit.return_value.stream.return_value = [python]
    assert writers.pending_created('synthetic', firestore_client=object()) == ['c']
    query.limit.return_value.stream.assert_called_once()
    query.start_after.assert_not_called()


@pytest.mark.parametrize('engine', ['pending', 'go'])
@pytest.mark.asyncio
async def test_marked_created_delivery_preserves_claim_and_owed_marker(strict, delivery, monkeypatch, engine):
    strict.rows[C] = derived(
        v3_notes_written=True, v3_created_pending=True, finalization_engine=engine, finalization_owner_epoch=1
    )
    blocked = dict(strict.rows[C])
    assert await created.deliver('synthetic') == 0
    assert strict.rows[C] == blocked

    strict.rows[C] = derived(v3_notes_written=True, v3_created_pending=True)

    def read_after_claim(*_):
        strict.rows[C].update(finalization_engine=engine, finalization_owner_epoch=1)
        return dict(strict.rows[C])

    monkeypatch.setattr(created.conversations_db, 'get_conversation', read_after_claim)
    assert await created.deliver('synthetic') == 0
    blocked = dict(strict.rows[C])
    assert not delivery.sent and not delivery.wakes
    assert blocked['v3_created_pending'] and blocked['v3_created_attempts'] == 1
    for delivered, dropped in [(True, False), (False, True), (False, False)]:
        assert not writers.finish_created('synthetic', 'c', 1, delivered=delivered, dropped=dropped)
        assert strict.rows[C] == blocked


@pytest.mark.asyncio
async def test_delivery_is_exactly_once_across_redrains_and_re_notes(strict, delivery):
    strict.rows[C] = derived()
    settle(strict)
    assert await created.deliver('synthetic') == 1
    assert await created.deliver('synthetic') == 0
    # A late rewrite or explicit Retry writes notes again; the conversation was already created.
    assert settle(strict) is False
    assert await created.deliver('synthetic') == 0
    assert len(delivery.sent) == 1
    uid, cid, kwargs = delivery.sent[0]
    assert (uid, cid) == ('synthetic', 'c')
    assert kwargs == {'idempotency_key': 'v3-created:c', 'require_delivery': True, 'last_delivery_attempt': False}
    assert strict.rows[C]['v3_created_pending'] is False and strict.rows[C]['v3_created_delivered_at']


@pytest.mark.asyncio
async def test_failed_delivery_stays_owed_and_wakes_the_owner_later(strict, delivery):
    strict.rows[C] = derived()
    settle(strict)
    delivery.failures.append(ExternalIntegrationFanoutError('1 durable integration deliveries failed'))
    before = datetime.now(timezone.utc)
    assert await created.deliver('synthetic') == 0
    assert strict.rows[C]['v3_created_pending'] is True and strict.rows[C]['v3_created_claim_until'] is None
    assert len(delivery.wakes) == 1 and delivery.wakes[0] - before >= created.RETRY - timedelta(seconds=1)
    assert await created.deliver('synthetic') == 1
    # The replay carries the same key, so a receiver that saw the first attempt deduplicates it.
    assert [kwargs['idempotency_key'] for _, _, kwargs in delivery.sent] == ['v3-created:c']


@pytest.mark.asyncio
async def test_final_attempt_drops_receiver_failures_instead_of_retrying(strict, delivery):
    strict.rows[C] = derived(v3_created_attempts=writers.CREATED_MAX_ATTEMPTS - 1)
    settle(strict)
    assert await created.deliver('synthetic') == 1
    assert delivery.sent[0][2]['last_delivery_attempt'] is True


@pytest.mark.asyncio
async def test_a_row_that_stops_qualifying_drops_its_obligation(strict, delivery):
    strict.rows[C] = derived()
    settle(strict)
    strict.rows[C]['deleted'] = True
    assert await created.deliver('synthetic') == 0
    assert delivery.sent == [] and strict.rows[C]['v3_created_pending'] is False


def test_live_claim_blocks_a_concurrent_deliverer_and_a_stale_finish(strict):
    strict.rows[C] = derived()
    settle(strict)
    first = writers.claim_created('synthetic', 'c', firestore_client=strict)
    assert first == 1
    assert writers.claim_created('synthetic', 'c', firestore_client=strict) is None
    # Expired claim: a successor takes attempt 2; the first worker's late finish is fenced out.
    strict.rows[C]['v3_created_claim_until'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert writers.claim_created('synthetic', 'c', firestore_client=strict) == 2
    assert not writers.finish_created('synthetic', 'c', first, delivered=True, firestore_client=strict)
    assert 'v3_created_delivered_at' not in strict.rows[C]


def test_claims_are_bounded_when_delivery_never_completes(strict):
    strict.rows[C] = derived(v3_created_attempts=writers.CREATED_MAX_ATTEMPTS + 1)
    settle(strict)
    assert writers.claim_created('synthetic', 'c', firestore_client=strict) is None
    assert strict.rows[C]['v3_created_pending'] is False


def _visible_rebuild(monkeypatch, prior):
    def build(uid, window, recordings, existing=None, *, allocated=None):
        return {
            **(existing or prior),
            'home_hidden': False,
            'home_hidden_reason': None,
            'status': 'processing',
            '_v3_claims': {},
        }

    monkeypatch.setattr(service.planner, 'build', build)
    monkeypatch.setattr(service.planner, 'late_rewrite', lambda **kw: False)
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda *a: None)


def _prior(**updates):
    return {
        'id': 'c',
        'v3_derived': True,
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'status': 'completed',
        'tile_state': 'done',
        'home_hidden': True,
        'v3_notes_written': True,
        'v3_recording_ids': ['r'],
        'transcript_segments': [{'text': 'speech for a synthetic plan', 'start': 0, 'end': 10}],
        '_v3_revision': 1,
        **updates,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'updates, owed',
    [
        ({}, True),
        ({'home_hidden': False}, False),
        ({'v3_notes_written': False}, False),
        ({'v3_created_delivered_at': AT}, False),
    ],
)
async def test_hidden_window_with_notes_owes_delivery_when_it_first_shows(builder, monkeypatch, updates, owed):
    committed, _ = builder
    prior = _prior(**updates)
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {'c': prior}, []))
    _visible_rebuild(monkeypatch, prior)
    assert await service.reconcile('u') == 'committed'
    rows = committed[0][4]
    assert [row['id'] for row in rows] == ['c']
    assert bool(rows[0].get('v3_created_pending')) is owed


def test_explicit_retry_settle_wakes_the_owner_to_deliver(monkeypatch):
    monkeypatch.setattr(processing.leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(processing.leases, 'keepalive', lambda *a: nullcontext())
    monkeypatch.setattr(processing.leases, 'release', lambda *a: None)
    monkeypatch.setattr(processing.fence, 'writer', lambda *a: nullcontext())
    monkeypatch.setattr(processing.models, 'notes_mode', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(processing.writers, 'begin_processing', lambda *a, **kw: True)
    settles = []
    monkeypatch.setattr(processing.writers, 'settle_processing', lambda *a, **kw: settles.append(kw) or True)
    wakes = []
    monkeypatch.setattr(processing, 'enqueue', lambda uid, at=None: wakes.append((uid, at)))
    conversation = SimpleNamespace(
        id='c',
        is_locked=False,
        finished_at=AT,
        tile_state=None,
        summary_retryable=None,
        model_dump=lambda: {'id': 'c', 'sync_content_revision': 1},
    )
    result = SimpleNamespace(
        status='completed', home_hidden=False, structured=SimpleNamespace(title='Plan'), tile_state=None
    )

    def fn(uid, language, conversation, *, persistence_observer, **kwargs):
        persistence_observer(True)
        return result

    assert processing.run_external(fn, 'u', 'en', conversation) is result
    assert settles[0]['notes'] is True
    assert len(wakes) == 1 and wakes[0][0] == 'u'


def test_exhausted_row_settles_as_a_no_op_instead_of_raising(monkeypatch):
    monkeypatch.setattr(processing.leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(processing.leases, 'keepalive', lambda *a: nullcontext())
    monkeypatch.setattr(processing.leases, 'release', lambda *a: None)
    monkeypatch.setattr(processing.fence, 'writer', lambda *a: nullcontext())
    monkeypatch.setattr(processing.writers, 'begin_processing', lambda *a, **kw: writers.TERMINAL)
    conversation = SimpleNamespace(id='c', is_locked=False, model_dump=lambda: {'id': 'c'})
    assert (
        processing.run_external(lambda *a, **kw: pytest.fail('paid work ran'), 'u', 'en', conversation) is conversation
    )


def test_unavailable_row_still_raises(monkeypatch):
    monkeypatch.setattr(processing.leases, 'acquire', lambda *a: 'token')
    monkeypatch.setattr(processing.leases, 'keepalive', lambda *a: nullcontext())
    monkeypatch.setattr(processing.leases, 'release', lambda *a: None)
    monkeypatch.setattr(processing.fence, 'writer', lambda *a: nullcontext())
    monkeypatch.setattr(processing.writers, 'begin_processing', lambda *a, **kw: False)
    conversation = SimpleNamespace(id='c', is_locked=False, model_dump=lambda: {'id': 'c'})
    with pytest.raises(RuntimeError, match='v3_processing_unavailable'):
        processing.run_external(lambda *a, **kw: pytest.fail('paid work ran'), 'u', 'en', conversation)


@pytest.mark.asyncio
async def test_a_full_page_schedules_a_continuation_for_the_rest(strict, delivery, monkeypatch):
    strict.rows[C] = derived()
    settle(strict)
    monkeypatch.setattr(writers, 'pending_created', lambda uid: ['c'] + [f'gone-{n}' for n in range(7)])
    assert await created.deliver('synthetic') == 1
    assert len(delivery.wakes) == 1


def test_on_open_notes_arm_a_completed_visible_row(strict, monkeypatch):
    monkeypatch.setattr(store, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(
        writers.conversations, '_prepare_conversation_for_write', lambda row, *a, **kw: {**row}, raising=False
    )
    strict.rows[C] = derived(tile_state='failed', v3_process_failed=True, structured={})
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert writers.store_summary('synthetic', 'c', token, 1, {'title': 'Plan'}, AT, firestore_client=strict) is True
    assert strict.rows[C]['v3_created_pending'] is True and strict.rows[C]['v3_notes_written'] is True
    strict.rows[C].update(v3_created_pending=False, v3_created_delivered_at=AT)
    assert writers.store_summary('synthetic', 'c', token, 1, {'title': 'Plan'}, AT, firestore_client=strict) is False


@pytest.mark.asyncio
async def test_a_row_that_turned_private_after_its_claim_is_never_sent(strict, delivery, monkeypatch):
    strict.rows[C] = derived()
    settle(strict)
    monkeypatch.setattr(
        created.conversations_db,
        'get_conversation',
        lambda uid, cid: {**strict.rows[C], 'data_protection_level': 'private'},
    )
    assert await created.deliver('synthetic') == 0
    assert delivery.sent == [] and strict.rows[C]['v3_created_pending'] is False
    assert 'v3_created_delivered_at' not in strict.rows[C]


@pytest.mark.asyncio
async def test_an_unreadable_payload_stays_owed_instead_of_counting_as_delivered(strict, delivery, monkeypatch):
    strict.rows[C] = derived()
    settle(strict)
    monkeypatch.setattr(created.conversations_db, 'get_conversation', lambda uid, cid: None)
    assert await created.deliver('synthetic') == 0
    assert delivery.sent == [] and strict.rows[C]['v3_created_pending'] is True
    assert 'v3_created_delivered_at' not in strict.rows[C] and len(delivery.wakes) == 1


@pytest.mark.asyncio
async def test_a_retry_wake_that_cannot_be_scheduled_fails_the_task(strict, delivery, monkeypatch):
    strict.rows[C] = derived()
    settle(strict)
    delivery.failures.append(ExternalIntegrationFanoutError('1 durable integration deliveries failed'))

    def unavailable(uid, at=None):
        raise RuntimeError('conversations_v3_task_target_unconfigured')

    monkeypatch.setattr(created, 'enqueue', unavailable)
    with pytest.raises(RuntimeError, match='unconfigured'):
        await created.deliver('synthetic')
    assert strict.rows[C]['v3_created_pending'] is True


@pytest.mark.asyncio
async def test_the_builder_drain_delivers_settled_notes(strict, delivery, monkeypatch):
    strict.rows[C] = derived()
    settle(strict)

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'pending_processing', lambda uid: [])
    await service.drain_processing('synthetic')
    assert [cid for _, cid, _ in delivery.sent] == ['c']
