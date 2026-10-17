"""Halt-at-cap: explicit month-scoped consent, estimates and transcript preservation."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils import funded_processing as funded, processing_backlog as backlog, processing_backlog_worker as worker
from models.conversation import Conversation, CreateConversation, ConversationSource, Structured
from models.transcript_segment import TranscriptSegment
from models.users import ProcessingBacklog, Subscription, UserSubscriptionResponse
from utils.conversations import process_conversation as pipeline
from routers import users as route


def allowance(remaining=130, managed=True):
    return SimpleNamespace(managed=managed, remaining_units=remaining, budget_units=1300)


def test_flags_off_add_no_reads_or_wire_fields(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setattr(backlog.store, 'read', Mock(side_effect=AssertionError('read')))
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
    monkeypatch.setattr(funded, 'enabled', lambda: True)
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


def test_upgrade_over_estimate_asks_but_explicit_choice_accepts_partial(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
    monkeypatch.setattr(funded, 'allowance', lambda uid: allowance())
    monkeypatch.setattr(
        backlog,
        'snapshot',
        lambda *a, **k: ProcessingBacklog(
            state='waiting_choice', remaining_units=130, estimated_units=260, exceeds_remaining=True
        ),
    )
    start = Mock(return_value={'token': 'new'})
    monkeypatch.setattr(backlog.store, 'start', start)
    assert backlog.choose('synthetic', request_key='synthetic-choice', automatic=True) is None
    assert start.call_args.kwargs['begin'] is False
    start.reset_mock()
    assert backlog.choose('synthetic', request_key='synthetic-choice')['token'] == 'new'
    assert start.call_args.kwargs['remaining'] == 130


@pytest.mark.parametrize('source', [ConversationSource.phone, ConversationSource.desktop, ConversationSource.omi])
@pytest.mark.parametrize('custom', [False, True])
def test_all_sources_store_transcript_without_paid_pipeline(monkeypatch, source, custom):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
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


def test_opening_existing_waiting_transcript_after_reset_does_not_process(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
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
    monkeypatch.setattr(funded, 'enabled', lambda: True)
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
        return True

    monkeypatch.setattr(worker, '_process', process)
    await worker.run('synthetic')
    assert processed == ['new', 'old']
    assert job['remaining'] == 1 and job['state'] == 'waiting_choice'
    assert job['reserved'] == {}


async def test_finishing_choice_schedules_an_already_accepted_upgrade(monkeypatch):
    import asyncio

    monkeypatch.setattr(funded, 'enabled', lambda: True)
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
    scheduled = []

    def schedule(coroutine, *, name):
        scheduled.append(name)
        if name == 'processing_backlog_continuation':
            coroutine.close()
            return None
        return asyncio.create_task(coroutine)

    monkeypatch.setattr(worker, 'start_background_task', schedule)
    await worker.run('synthetic')
    finished.assert_called_once_with('synthetic', 'choice', 'lease', '2026-10')
    assert scheduled == ['processing_backlog_lease', 'processing_backlog_continuation']


async def test_previous_month_intent_cannot_spend_the_new_month(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
    monkeypatch.setattr(funded, 'period_id', lambda: '2026-11')
    monkeypatch.setattr(worker.cap_hold, 'recovery_cooldown', lambda uid: True)
    monkeypatch.setattr(worker.store, 'read', lambda uid: {'state': 'processing', 'period': '2026-10'})
    claim = Mock(side_effect=AssertionError('old consent acquired new month'))
    monkeypatch.setattr(worker.store, 'claim', claim)
    await worker.run('synthetic')
    claim.assert_not_called()


def test_authenticated_process_endpoint_requires_replay_key_and_preserves_backend_estimate(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
    choice = Mock(return_value={'token': 'run'})
    monkeypatch.setattr(backlog, 'choose', choice)
    snapshot = ProcessingBacklog(
        state='processing', estimated_units=130, estimated_hours=1, estimated_percent=10, exceeds_remaining=True
    )
    monkeypatch.setattr(backlog, 'snapshot', lambda uid: snapshot)
    kicked = Mock()
    monkeypatch.setattr(route, 'kick_processing_backlog', kicked)
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
    kicked.assert_called_once_with('synthetic')


def test_renewals_and_downgrades_do_not_create_upgrade_intent():
    from models.users import PlanType

    old = Subscription(plan=PlanType.plus, current_price_id='legacy-plus', current_period_end=1)
    renewed = old.model_copy(update={'current_period_end': 2_000_000_000})
    assert not backlog.allowance_increased(old, renewed)
    basic = Subscription(plan=PlanType.basic)
    assert not backlog.allowance_increased(old, basic)
    assert backlog.allowance_increased(basic, renewed)


def test_capped_empty_backlog_still_publishes_pause_state(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
    result = backlog.snapshot('synthetic', allowance=allowance(0, False), audio={'count': 0, 'seconds': 0}, summary={})
    assert result.state == 'capped' and result.held_audio_count == 0


def test_unavailable_allowance_never_claims_monthly_limit_exhaustion(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda: True)
    result = backlog.snapshot(
        'synthetic',
        allowance=SimpleNamespace(managed=False, reason='allowance_unavailable', remaining_seconds=0, limit_seconds=0),
        audio={'count': 1, 'seconds': 60},
        summary={},
    )
    assert result.state == 'capped' and result.budget_exhausted is False
