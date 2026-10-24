"""Halt-at-cap: explicit month-scoped consent, estimates and transcript preservation."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils import funded_processing as funded, processing_backlog as backlog, processing_backlog_worker as worker
from models.conversation import Conversation, CreateConversation, ConversationSource, Structured
from models.transcript_segment import TranscriptSegment
from models.users import ProcessingBacklog, Subscription, UserSubscriptionResponse
from utils.conversations import process_conversation as pipeline
from routers import users as route


@pytest.fixture(autouse=True)
def no_cap_hold_reservations(monkeypatch):
    # Cap-hold batch reservations (lane 6) are covered by test_cap_hold_batch_debit.py; here none are open.
    monkeypatch.setattr(worker.cap_hold_reservations, 'open_units', lambda *args, **kwargs: 0.0)


def allowance(remaining=130, managed=True):
    return SimpleNamespace(managed=managed, remaining_units=remaining, budget_units=1300)


def test_flags_off_add_no_reads_or_wire_fields(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setattr(worker.store, 'read', Mock(side_effect=AssertionError('read')))
    assert backlog.snapshot('synthetic') is None
    assert backlog.choose('synthetic', request_key='synthetic-choice') is None
    app = FastAPI()
    response = UserSubscriptionResponse(
        subscription=Subscription(),
        transcription_seconds_used=0,
        transcription_seconds_limit=0,
        words_transcribed_used=0,
        words_transcribed_limit=0,
        insights_gained_used=0,
        insights_gained_limit=0,
    )
    app.get('/subscription', response_model=UserSubscriptionResponse)(lambda: response)
    with TestClient(app) as client:
        data = client.get('/subscription').json()
    assert 'processing_backlog' not in data and 'held_audio' not in data
    assert data['phone_call_quota'] is None


@pytest.mark.parametrize(
    'managed,period,expected',
    [(False, '2026-10', 'capped'), (True, '2026-09', 'waiting_choice'), (True, '2026-10', 'processing')],
)
def test_reset_keeps_backlog_waiting_and_estimates_from_totals(monkeypatch, managed, period, expected):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-10')
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    result = backlog.snapshot(
        'synthetic',
        allowance=allowance(65, managed),
        audio={'count': 300, 'seconds': 3600},
        summary={'count': 2, 'units': 130, 'state': 'processing', 'period': period},
    )
    assert result.state == expected
    assert result.held_audio_count == 300 and result.deferred_conversations == 2
    assert result.estimated_units == 260 and result.estimated_hours == 2
    assert result.estimated_percent == 20 and result.exceeds_remaining


def test_estimated_percent_rounds_half_up_to_a_whole_number(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-10')
    allowance = SimpleNamespace(managed=True, remaining_units=1000, budget_units=1000)
    summary = {'count': 1, 'units': 125, 'seconds': 0, 'state': 'waiting_choice', 'period': '2026-09'}
    result = backlog.snapshot('synthetic', allowance=allowance, audio={'count': 0, 'seconds': 0}, summary=summary)
    assert result.estimated_percent == 13
    summary['units'] = 124
    result = backlog.snapshot('synthetic', allowance=allowance, audio={'count': 0, 'seconds': 0}, summary=summary)
    assert result.estimated_percent == 12
    assert backlog.whole_percent(0) == 0


def test_upgrade_over_estimate_asks_but_explicit_choice_accepts_partial(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance())
    monkeypatch.setattr(
        backlog,
        'snapshot',
        lambda *a, **k: ProcessingBacklog(
            state='waiting_choice', remaining_units=130, estimated_units=260, exceeds_remaining=True
        ),
    )
    start = Mock(return_value={'token': 'new'})
    monkeypatch.setattr(worker.store, 'start', start)
    assert backlog.choose('synthetic', request_key='synthetic-choice', automatic=True) is None
    assert start.call_args.kwargs['begin'] is False
    start.reset_mock()
    assert backlog.choose('synthetic', request_key='synthetic-choice')['token'] == 'new'
    assert start.call_args.kwargs['remaining'] == 130


@pytest.mark.parametrize('source', [ConversationSource.phone, ConversationSource.desktop, ConversationSource.omi])
@pytest.mark.parametrize('custom', [False, True])
def test_all_sources_store_transcript_without_paid_pipeline(monkeypatch, source, custom):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'processing_allowed', lambda uid: False)
    now = datetime.now(timezone.utc)
    raw = CreateConversation(
        source=source,
        started_at=now,
        finished_at=now + timedelta(seconds=60),
        transcript_segments=[
            TranscriptSegment(is_user=True, text='This transcript must remain visible.', start=0, end=60)
        ],
        uses_custom_stt=custom,
    )
    saved = Mock(return_value=True)
    monkeypatch.setattr(pipeline.lifecycle_service, 'create_completed_conversation', saved)
    monkeypatch.setattr(
        pipeline, '_enrich_meeting_context', Mock(side_effect=AssertionError('managed pipeline entered'))
    )
    dispositions = []
    result = pipeline.process_conversation(
        'synthetic', 'en', raw, derived_effects_disposition_observer=dispositions.append
    )
    assert result.processing_deferred and result.status.value == 'completed'
    assert result.transcript_segments[0].text == raw.transcript_segments[0].text
    assert not result.discarded
    payload = saved.call_args.args[1]
    assert payload['processing_deferred']
    assert payload['external_data']['processing_backlog_estimate']['units'] > 0
    assert dispositions == [pipeline.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]


@pytest.mark.parametrize('initial', [True, False])
def test_waiting_projection_stays_display_only_and_never_overwrites_an_existing_row(monkeypatch, initial):
    from models.client_processing import ClientProcessing, ProjectedStructure, ProjectionProvenance

    now = datetime.now(timezone.utc)
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256='ab' * 32,
        structure=ProjectedStructure(title='Untrusted display sentinel'),
        provenance=ProjectionProvenance(model_id='local', runtime='test', device_class='phone', generated_at=now),
    )
    fields = dict(
        started_at=now,
        finished_at=now + timedelta(seconds=60),
        transcript_segments=[TranscriptSegment(is_user=True, text='Original captured words', start=0, end=60)],
    )
    incoming = (
        CreateConversation(**fields)
        if initial
        else Conversation(id='existing', created_at=now, structured=Structured(title='Server structure'), **fields)
    )
    create, persist = Mock(return_value=True), Mock(return_value=True)
    monkeypatch.setattr(pipeline.lifecycle_service, 'create_completed_conversation', create)
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', persist)
    result, _ = pipeline._store_budget_waiting('synthetic', incoming, client_projection=projection)
    payload = (create if initial else persist).call_args.args[1]
    assert result.client_processing == projection
    assert 'Untrusted display sentinel' not in str(payload['structured'])
    assert payload['processing_deferred'] is True
    if initial:
        assert payload['client_processing']['structure']['title'] == 'Untrusted display sentinel'
        persist.assert_not_called()
    else:
        assert 'client_processing' not in payload
        create.assert_not_called()


def test_opening_existing_waiting_transcript_after_reset_does_not_process(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'processing_allowed', lambda uid: True)
    monkeypatch.setattr(pipeline, '_enrich_meeting_context', Mock(side_effect=AssertionError('automatic processing')))
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', Mock(return_value=True))
    conv = Conversation(
        id='waiting',
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        structured=Structured(),
        processing_deferred=True,
        transcript_segments=[TranscriptSegment(is_user=True, text='Saved text', start=0, end=1)],
    )
    result = pipeline.process_conversation('synthetic', 'en', conv)
    assert result.processing_deferred and result.transcript_segments[0].text == 'Saved text'


async def test_explicit_worker_selects_newest_first_and_leaves_unfitting_rows(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-10')
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance(10))
    job = {
        'state': 'processing',
        'period': '2026-10',
        'token': 'choice',
        'cutoff': 100,
        'remaining': 10,
        'reserved': {},
    }
    monkeypatch.setattr(worker.store, 'read', lambda uid: dict(job))
    monkeypatch.setattr(worker.store, 'claim', lambda *args: 'lease')

    def save(uid, token, lease, updates):
        assert token == 'choice' and lease == 'lease'
        job.update(updates)
        return True

    monkeypatch.setattr(worker.store, 'checkpoint', save)

    def finish(uid, token, lease, period):
        assert period == '2026-10'
        save(uid, token, lease, {'state': 'waiting_choice'})
        return False

    monkeypatch.setattr(worker.store, 'finish', finish)
    rows = [
        (
            'text',
            SimpleNamespace(
                id=name, to_dict=lambda at=at, units=units: {'started_at': at, 'queued_at': 50, 'units': units}
            ),
        )
        for name, at, units in [('old', 1, 3), ('middle', 2, 8), ('new', 3, 6)]
    ]
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: rows if kind == 'text' else [])
    processed = []

    async def process(uid, item):
        processed.append(item['id'])
        return worker.AttemptOutcome.COMPLETE

    monkeypatch.setattr(worker, '_process', process)
    await worker.run('synthetic')
    assert processed == ['new', 'old']
    assert job['remaining'] == 1 and job['state'] == 'waiting_choice'
    assert job['reserved'] == {}


async def test_finishing_choice_schedules_an_already_accepted_upgrade(monkeypatch):
    import asyncio

    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-10')
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(
        worker.store,
        'read',
        lambda uid: {
            'state': 'processing',
            'period': '2026-10',
            'token': 'choice',
            'reserved': {},
        },
    )
    monkeypatch.setattr(worker.store, 'claim', lambda *args: 'lease')
    monkeypatch.setattr(worker.store, 'checkpoint', lambda *args: False)
    finished = Mock(return_value=True)
    monkeypatch.setattr(worker.store, 'finish', finished)
    monkeypatch.setattr(worker, '_page', lambda *args: [])
    await worker.run('synthetic')
    finished.assert_called_once_with('synthetic', 'choice', 'lease', '2026-10')
    # The accepted upgrade remains durable for the next scheduler sweep.


async def test_previous_month_intent_cannot_spend_the_new_month(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: {'state': 'processing', 'period': '2026-10'})
    claim = Mock(side_effect=AssertionError('old consent acquired new month'))
    monkeypatch.setattr(worker.store, 'claim', claim)
    await worker.run('synthetic')
    claim.assert_not_called()


def test_authenticated_process_endpoint_requires_replay_key_and_preserves_backend_estimate(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    choice = Mock(return_value={'token': 'run'})
    monkeypatch.setattr(backlog, 'choose', choice)
    snapshot = ProcessingBacklog(
        state='processing', estimated_units=130, estimated_hours=1, estimated_percent=10, exceeds_remaining=True
    )
    monkeypatch.setattr(backlog, 'snapshot', lambda uid: snapshot)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: 'synthetic'
    with TestClient(app) as client:
        assert client.post('/v1/users/processing-backlog/process').status_code == 422
        response = client.post(
            '/v1/users/processing-backlog/process', headers={'Idempotency-Key': 'synthetic-choice-uuid'}
        )
    assert response.status_code == 200, response.text
    assert response.json()['estimated_percent'] == 10
    assert response.json()['exceeds_remaining'] is True
    choice.assert_called_once_with('synthetic', request_key='synthetic-choice-uuid')


def test_renewals_and_downgrades_do_not_create_upgrade_intent():
    from models.users import PlanType

    old = Subscription(plan=PlanType.plus, current_price_id='legacy-plus', current_period_end=1)
    renewed = old.model_copy(update={'current_period_end': 2_000_000_000})
    assert not backlog.allowance_increased(old, renewed)
    basic = Subscription(plan=PlanType.basic)
    assert not backlog.allowance_increased(old, basic)
    assert backlog.allowance_increased(basic, renewed)


def test_capped_empty_backlog_still_publishes_pause_state(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    result = backlog.snapshot('synthetic', allowance=allowance(0, False), audio={'count': 0, 'seconds': 0}, summary={})
    assert result.state == 'capped' and result.held_audio_count == 0


def test_unavailable_allowance_never_claims_monthly_limit_exhaustion(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    result = backlog.snapshot(
        'synthetic',
        allowance=SimpleNamespace(managed=False, reason='allowance_unavailable', remaining_seconds=0, limit_seconds=0),
        audio={'count': 1, 'seconds': 60},
        summary={},
    )
    assert result.state == 'capped' and result.budget_exhausted is False


@pytest.mark.parametrize('trigger', list(pipeline.ProcessingTrigger))
def test_cap_denial_preserves_existing_enrichment_and_discard_state(monkeypatch, trigger):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'processing_allowed', lambda uid: False)
    now = datetime.now(timezone.utc)
    conv = Conversation(
        id='enriched',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(title='Existing title', overview='Existing summary'),
        discarded=True,
        transcript_segments=[TranscriptSegment(is_user=True, text='Stored transcript', start=0, end=1)],
    )
    before = conv.model_dump()
    persist = Mock(side_effect=AssertionError('enrichment overwritten'))
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', persist)
    monkeypatch.setattr(pipeline, '_enrich_meeting_context', Mock(side_effect=AssertionError('funded work')))
    dispositions, persistence = [], []
    if trigger is pipeline.ProcessingTrigger.SILENT_BACKFILL:
        # Silent backfill is the one trigger whose cap denial must not return
        # the preserved row: its caller is a leased historical finalization
        # job, and a quiet return (or the budget-waiting store the generic
        # path takes for a raw row) would let the finalizer close the job as a
        # successful backfill. It raises the recovery failure before any
        # persistence instead (#23260), so the same preservation invariant is
        # asserted through the raise: no funded work, no write, no observer
        # events, and the row's enrichment and discard state untouched.
        with pytest.raises(pipeline.RecoveryStructureUnavailableError):
            pipeline.process_conversation(
                'synthetic',
                'en',
                conv,
                trigger=trigger,
                persistence_observer=persistence.append,
                derived_effects_disposition_observer=dispositions.append,
            )
        assert conv.model_dump() == before
        assert persistence == []
        assert dispositions == []
        persist.assert_not_called()
        return
    result = pipeline.process_conversation(
        'synthetic',
        'en',
        conv,
        trigger=trigger,
        persistence_observer=persistence.append,
        derived_effects_disposition_observer=dispositions.append,
    )
    assert result.model_dump() == before
    assert persistence == [False]
    assert dispositions == [pipeline.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]
    persist.assert_not_called()


@pytest.mark.parametrize(
    'intent_at,accepted',
    [
        (datetime(2026, 1, 31, tzinfo=timezone.utc).timestamp(), False),
        (datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp(), True),
        (None, False),
        ('malformed', False),
    ],
)
def test_late_first_upgrade_delivery_cannot_spend_new_month(monkeypatch, intent_at, accepted):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-02')
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance())
    monkeypatch.setattr(
        backlog,
        'snapshot',
        lambda *a, **k: ProcessingBacklog(
            state='waiting_choice', remaining_units=130, estimated_units=10, exceeds_remaining=False
        ),
    )
    start = Mock(return_value={'state': 'processing', 'period': '2026-02'})
    monkeypatch.setattr(worker.store, 'start', start)
    result = backlog.choose('synthetic', request_key='upgrade-first-delivery', automatic=True, intent_at=intent_at)
    assert (result is not None) is accepted
    assert start.call_args.kwargs['begin'] is accepted
    assert start.call_args.kwargs['period'] == '2026-02'


def test_precreated_on_device_ingress_still_becomes_waiting(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'processing_allowed', lambda uid: False)
    now = datetime.now(timezone.utc)
    conv = Conversation(
        id='precreated',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(),
        status='processing',
        transcript_segments=[TranscriptSegment(is_user=True, text='Raw on-device text', start=0, end=1)],
    )
    persist = Mock(return_value=True)
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', persist)
    result = pipeline.process_conversation('synthetic', 'en', conv)
    assert result.processing_deferred and result.status.value == 'completed'
    assert result.transcript_segments[0].text == 'Raw on-device text'
    assert persist.call_args.args[1]['processing_deferred'] is True


@pytest.mark.parametrize('existing', [False, True])
def test_later_dispatch_denial_keeps_capture_instead_of_ingress_cleanup(monkeypatch, existing):
    from fastapi import HTTPException

    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    now = datetime.now(timezone.utc)
    fields = dict(
        started_at=now,
        finished_at=now,
        transcript_segments=[TranscriptSegment(is_user=True, text='Must survive mid-pipeline cap', start=0, end=1)],
    )
    captured = (
        Conversation(
            id='enriched', created_at=now, structured=Structured(title='Old summary'), discarded=True, **fields
        )
        if existing
        else CreateConversation(**fields)
    )
    create = Mock(return_value=True)
    persist = Mock(side_effect=AssertionError('existing enrichment overwritten'))
    monkeypatch.setattr(pipeline.lifecycle_service, 'create_completed_conversation', create)
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', persist)

    @pipeline._preserve_capture_on_budget_denial
    def pipeline_that_crosses_cap(uid, language, conversation):
        raise HTTPException(status_code=402, detail={'error': 'usage_budget_exhausted'})

    result = pipeline_that_crosses_cap('synthetic', 'en', captured)
    assert result.transcript_segments[0].text == 'Must survive mid-pipeline cap'
    if existing:
        assert result.model_dump() == captured.model_dump()
        create.assert_not_called()
    else:
        assert result.processing_deferred
        create.assert_called_once()
    persist.assert_not_called()


def test_rollover_during_choice_never_stamps_old_intent_with_new_month(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    month = Mock(side_effect=['2026-01', '2026-02'])
    monkeypatch.setattr(funded, 'period_id', month)
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance())
    monkeypatch.setattr(
        backlog,
        'snapshot',
        lambda *a, **k: ProcessingBacklog(
            state='waiting_choice', remaining_units=130, estimated_units=10, exceeds_remaining=False
        ),
    )
    start = Mock(return_value={'period': '2026-01'})
    monkeypatch.setattr(worker.store, 'start', start)
    result = backlog.choose(
        'synthetic',
        request_key='rollover-upgrade',
        automatic=True,
        intent_at=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp(),
    )
    assert result['period'] == '2026-01'
    assert start.call_args.kwargs['period'] == '2026-01'
    month.assert_called_once()


async def test_reserved_attempt_does_not_dispatch_if_month_rolls_during_claim(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', Mock(side_effect=['2026-01', '2026-01', '2026-02']))
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(
        worker.store,
        'read',
        lambda uid: {'state': 'processing', 'period': '2026-01', 'token': 'old', 'reserved': {'id': 'reserved'}},
    )
    monkeypatch.setattr(worker.store, 'claim', lambda *args: 'lease')
    monkeypatch.setattr(worker.store, 'checkpoint', lambda *args: True)
    from unittest.mock import AsyncMock

    process = AsyncMock(side_effect=AssertionError('old month dispatched'))
    monkeypatch.setattr(worker, '_process', process)
    await worker.run('synthetic')
    process.assert_not_called()


async def test_worker_dispatch_carries_expiring_month_consent(monkeypatch):
    from unittest.mock import AsyncMock

    month = ['2026-10']
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'period_id', lambda: month[0])
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance())
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    job = {
        'state': 'processing',
        'period': '2026-10',
        'token': 'choice',
        'cutoff': 100,
        'remaining': 130,
        'reserved': {},
    }
    monkeypatch.setattr(worker.store, 'read', lambda uid: dict(job))
    monkeypatch.setattr(worker.store, 'claim', lambda *args: 'lease')
    monkeypatch.setattr(worker.store, 'checkpoint', lambda uid, token, lease, updates: job.update(updates) or True)
    monkeypatch.setattr(worker.store, 'finish', lambda *args: False)
    row = SimpleNamespace(id='text', to_dict=lambda: {'started_at': 5, 'queued_at': 50, 'units': 3})
    monkeypatch.setattr(worker, '_page', lambda uid, kind, cursor: [('text', row)] if kind == 'text' else [])

    async def process(uid, item):
        assert funded.processing_allowed(uid)
        month[0] = '2026-11'
        assert not funded.processing_allowed(uid)
        return worker.AttemptOutcome.DEFERRED

    process_mock = AsyncMock(side_effect=process)
    monkeypatch.setattr(worker, '_process', process_mock)
    await worker.run('synthetic')
    process_mock.assert_called_once()
    assert not job['reserved']
    assert funded.processing_allowed('synthetic')  # New capture has no expired job grant.


@pytest.mark.parametrize('flag', ['LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'STT_CAP_DISPATCH_ENFORCEMENT'])
@pytest.mark.parametrize('summary_switch', [None, 'false'])
def test_funded_cap_denial_stores_summary_as_waiting_never_terminal_or_derived(monkeypatch, flag, summary_switch):
    from models.client_processing import ClientProcessing, ProjectedStructure, ProjectionProvenance
    from utils.conversations.processing_trigger import ProcessingTrigger

    for key in ('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'STT_CAP_DISPATCH_ENFORCEMENT'):
        monkeypatch.setenv(key, 'true' if key == flag else 'false')
    monkeypatch.delenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', raising=False)
    if summary_switch is not None:
        monkeypatch.setenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', summary_switch)
    # Legacy rollout values cannot reactivate terminal minimum processing.
    monkeypatch.setenv('FREE_TIER_LOCAL_PROCESSING', 'true')
    monkeypatch.setenv('FREE_TIER_LOCAL_PROCESSING_COHORT', 'pct:100')
    monkeypatch.setenv('BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED', 'true')
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance(0, False))
    now = datetime.now(timezone.utc)
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256='ab' * 32,
        structure=ProjectedStructure(title='Local display only'),
        provenance=ProjectionProvenance(model_id='afm', runtime='local', device_class='mac', generated_at=now),
    )
    raw = CreateConversation(
        source=ConversationSource.desktop,
        started_at=now,
        finished_at=now,
        transcript_segments=[TranscriptSegment(text='Captured original', start=0, end=1, is_user=True)],
    )
    saved = Mock(return_value=True)
    monkeypatch.setattr(pipeline.lifecycle_service, 'create_completed_conversation', saved)
    forbidden = Mock(side_effect=AssertionError('provider or derived work'))
    for name in (
        '_get_structured',
        '_extract_memories',
        '_save_action_items',
        'submit_with_context',
        'trigger_conversation_apps',
        '_enrich_meeting_context',
    ):
        monkeypatch.setattr(pipeline, name, forbidden)
    result = pipeline.process_conversation('synthetic', 'en', raw, client_projection=projection)
    assert result.processing_deferred and not result.deferred
    assert result.client_processing == (projection if summary_switch is None else None)
    assert result.structured.title == 'Captured original'
    payload = saved.call_args.args[1]
    assert ('client_processing' in payload) is (summary_switch is None)
    assert payload['processing_deferred'] is True
    # Rollback preserves a stored display projection. Reset and ordinary reprocess
    # never start work or consume consent.
    monkeypatch.setenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', 'false')
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance(130, True))
    persist = Mock(return_value=True)
    monkeypatch.setattr(pipeline.lifecycle_service, 'persist_processed_conversation', persist)
    for trigger in (ProcessingTrigger.FIRST_OPEN, ProcessingTrigger.USER_REPROCESS, ProcessingTrigger.SYNC_UPDATE):
        retried = pipeline.process_conversation('synthetic', 'en', result, trigger=trigger)
        assert retried.processing_deferred
        assert retried.client_processing == result.client_processing
        assert 'client_processing' not in persist.call_args.args[1]
    forbidden.assert_not_called()


@pytest.mark.parametrize('update_only', [False, True])
def test_budget_waiting_vector_writer_never_calls_provider_after_reset(monkeypatch, update_only):
    now = datetime.now(timezone.utc)
    waiting = Conversation(
        id='waiting',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(title='Raw placeholder'),
        processing_deferred=True,
    )
    forbidden = Mock(side_effect=AssertionError('unchosen backlog vector work'))
    for name in (
        'generate_embedding',
        'update_vector_metadata',
        'upsert_vector2',
        'retrieve_metadata_fields_from_structured',
    ):
        monkeypatch.setattr(pipeline, name, forbidden)
    monkeypatch.setattr(funded, 'processing_allowed', lambda uid: True)
    assert pipeline.save_structured_vector('synthetic', waiting, update_only=update_only) is False
    forbidden.assert_not_called()
