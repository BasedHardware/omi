"""API contracts for the journal-owned materialization fetch/ack boundary."""

from datetime import datetime, timezone
import logging
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from models.chat_first import (
    ChatFirstSubject,
    ConversationLinkSpec,
    ProactiveIntent,
    QuestionCardSpec,
    QuestionOption,
)
from models.task_intelligence import TaskWorkflowControl
import routers.chat_first as chat_first_router


def _batch(intents, *, stalled_source=None):
    return chat_first_router.chat_first_intents_db.ReadyIntentBatch(intents, (), stalled_source)


def _empty_release_batch(*args, **kwargs):
    return chat_first_router.chat_first_intents_db.DeferralReleaseBatch(intents=[], malformed_count=0)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_first_router.router)
    current_auth = chat_first_router.auth.get_current_user_uid
    app.dependency_overrides[current_auth] = lambda: 'user-1'
    # Some older test modules replace ``utils.other.endpoints`` while pytest is
    # collecting. Override the callable captured by each route as well as the
    # current module attribute so these contracts do not depend on import order.
    for route in app.routes:
        dependant = getattr(route, 'dependant', None)
        for dependency in getattr(dependant, 'dependencies', []):
            if getattr(dependency.call, '__name__', None) == 'get_current_user_uid':
                app.dependency_overrides[dependency.call] = lambda: 'user-1'
    return TestClient(app)


def _request(
    *,
    generation: int = 7,
    owner_fence: str = 'user-1',
    receipts=None,
    terminal_receipts=None,
    rejections=None,
    deferrals=None,
) -> dict:
    return {
        'source_surface': 'main_chat',
        'control_generation': generation,
        'owner_fence': owner_fence,
        'window_foreground': True,
        'initial_page_loaded': True,
        'receipts': receipts or [],
        'rejections': rejections or [],
        'deferrals': deferrals or [],
        'cold_start_sequence_terminal_receipts': terminal_receipts or [],
    }


def _enable_chat_first(monkeypatch, *, generation: int = 7) -> None:
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(
            workflow_mode='read', account_generation=generation, chat_first_ui_enabled=True
        ),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )


def _question() -> QuestionCardSpec:
    return QuestionCardSpec(
        type='questionCard',
        question_id='question-1',
        text='What should happen next?',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        options=[QuestionOption(option_id='yes', label='Yes', prepared_answer='Yes')],
    )


def test_materialize_capability_off_does_zero_feature_store_or_metric_work(monkeypatch):
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7, chat_first_ui_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    for name in (
        'acknowledge_materialization',
        'acknowledge_sparse_cold_start_sequence_terminal',
        'record_materialization_rejection',
        'release_due_deferrals',
        'fetch_ready_intent_batch',
    ):
        monkeypatch.setattr(
            chat_first_router.chat_first_intents_db,
            name,
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f'{name} must not run')),
        )
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: (_ for _ in ()).throw(AssertionError('metric must not run'))),
    )

    response = _client().post('/v1/chat/materialize-prompts', json=_request())

    assert response.status_code == 404
    assert response.json() == {'detail': 'Not found'}


def test_materialize_rejects_wrong_owner_or_generation_before_feature_store_reads(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'fetch_ready_intent_batch',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('feature store must not run')),
    )

    wrong_owner = _client().post('/v1/chat/materialize-prompts', json=_request(owner_fence='another-user'))
    stale = _client().post('/v1/chat/materialize-prompts', json=_request(generation=6))

    assert wrong_owner.status_code == 404
    assert stale.status_code == 409


def test_materialize_returns_ready_intents_and_acknowledges_only_kernel_receipts(monkeypatch):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-1',
        continuity_key='goal-1-complete',
        account_generation=7,
        source='agent_judgment',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    acknowledgements = []
    terminal_acknowledgements = []
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'acknowledge_materialization',
        lambda *args, **kwargs: acknowledgements.append(kwargs) or intent,
    )
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'acknowledge_sparse_cold_start_sequence_terminal',
        lambda *args, **kwargs: terminal_acknowledgements.append(kwargs) or intent,
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *args, **kwargs: _batch([intent])
    )

    response = _client().post(
        '/v1/chat/materialize-prompts',
        json=_request(
            receipts=[{'intent_id': 'intent-1', 'receipt_id': 'kernel-receipt-1'}],
            terminal_receipts=[
                {
                    'sequence_id': 'cold-start:7',
                    'receipt_id': 'sequence-terminal-1',
                    'terminal_state': 'completed',
                }
            ],
        ),
    )

    assert response.status_code == 200
    assert len(acknowledgements) == 1
    assert acknowledgements[0]['intent_id'] == 'intent-1'
    assert acknowledgements[0]['receipt_id'] == 'kernel-receipt-1'
    assert acknowledgements[0]['account_generation'] == 7
    assert len(terminal_acknowledgements) == 1
    assert terminal_acknowledgements[0]['sequence_id'] == 'cold-start:7'
    assert terminal_acknowledgements[0]['receipt_id'] == 'sequence-terminal-1'
    assert terminal_acknowledgements[0]['terminal_state'] == 'completed'
    assert terminal_acknowledgements[0]['account_generation'] == 7
    assert terminal_acknowledgements[0]['now'].tzinfo is not None
    assert response.json()['intents'][0]['intent_id'] == 'intent-1'
    assert response.json()['intents'][0]['delivery_state'] == 'ready'


def test_materialize_records_typed_rejections_and_dead_letter_metric(monkeypatch):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-poison',
        continuity_key='capture:poison',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='poison'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    recorded = []
    metric_events = []
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'record_materialization_rejection',
        lambda *args, **kwargs: recorded.append(kwargs) or (intent, 'permanent_rejection:invalid_intent'),
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'fetch_ready_intent_batch',
        lambda *args, **kwargs: _batch([]),
    )
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: metric_events.append(kwargs))),
    )
    monkeypatch.setattr(
        'utils.chat_first_materialize_queue.CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: metric_events.append(kwargs))),
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(
            rejections=[{'intent_id': intent.intent_id, 'code': 'invalid_intent', 'message': 'Invalid block'}]
        ),
    )

    assert response.status_code == 200
    assert recorded[0]['intent_id'] == intent.intent_id
    assert recorded[0]['code'] == 'invalid_intent'
    assert {'event': 'rejected', 'source': 'capture_arrival', 'reason': 'invalid_intent'} in metric_events
    assert {
        'event': 'dead_letter',
        'source': 'capture_arrival',
        'reason': 'permanent_rejection:invalid_intent',
    } in metric_events
    assert {
        'event': 'materialize_batch_rejected',
        'source': 'materialization',
        'reason': 'all_hard_reject',
    } in metric_events
    assert response.json()['rejection_outcomes'] == [{'intent_id': 'intent-poison', 'outcome': 'recorded'}]


def test_one_malformed_intent_with_pending_rejection_never_fails_batch_and_sibling_is_recorded(monkeypatch):
    _enable_chat_first(monkeypatch)
    healthy = ProactiveIntent(
        intent_id='intent-healthy-rejection',
        continuity_key='healthy-rejection',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='healthy-rejection'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    calls = []

    def record_rejection(*args, **kwargs):
        calls.append(kwargs['intent_id'])
        if kwargs['intent_id'] == 'intent-malformed-rejection':
            raise chat_first_router.chat_first_intents_db.ChatFirstMalformedDocument('malformed intent')
        return healthy, None

    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'record_materialization_rejection', record_rejection)
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *args, **kwargs: _batch([])
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(
            rejections=[
                {'intent_id': 'intent-malformed-rejection', 'code': 'invalid_intent'},
                {'intent_id': healthy.intent_id, 'code': 'kernel_materialization_failed'},
            ]
        ),
    )

    assert response.status_code == 200
    assert calls == ['intent-malformed-rejection', healthy.intent_id]
    assert response.json()['rejection_outcomes'] == [
        {'intent_id': 'intent-malformed-rejection', 'outcome': 'malformed'},
        {'intent_id': healthy.intent_id, 'outcome': 'recorded'},
    ]


def test_one_invalid_receipt_never_fails_the_materialization_batch(monkeypatch):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-good',
        continuity_key='good',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='good'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    calls = []

    def acknowledge(*args, **kwargs):
        calls.append(kwargs['intent_id'])
        if kwargs['intent_id'] == 'intent-terminal':
            raise chat_first_router.chat_first_intents_db.ProactiveIntentNotReady('terminal')
        return intent.model_copy(update={'delivery_state': 'delivered'})

    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'acknowledge_materialization', acknowledge)
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *args, **kwargs: _batch([])
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(
            receipts=[
                {'intent_id': 'intent-terminal', 'receipt_id': 'receipt-terminal'},
                {'intent_id': 'intent-good', 'receipt_id': 'receipt-good'},
            ]
        ),
    )

    assert response.status_code == 200
    assert calls == ['intent-terminal', 'intent-good']
    assert response.json()['receipt_outcomes'] == [
        {'intent_id': 'intent-terminal', 'outcome': 'missing'},
        {'intent_id': 'intent-good', 'outcome': 'acknowledged'},
    ]


@pytest.mark.parametrize(
    ('outcome', 'failure'),
    [
        ('acknowledged', None),
        ('conflict', chat_first_router.chat_first_intents_db.ChatFirstIntentConflictError('conflict')),
        ('missing', chat_first_router.chat_first_intents_db.ProactiveIntentNotReady('missing')),
        (
            'generation_mismatch',
            chat_first_router.chat_first_intents_db.ChatFirstIntentDocumentGenerationMismatch('stale'),
        ),
    ],
)
def test_kernel_receipt_metric_labels_each_outcome_and_warns_only_for_conflicts(monkeypatch, outcome, failure):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-receipt-observability',
        continuity_key='receipt-observability',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='receipt-observability'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        delivery_state='delivered',
        materialization_receipt_id='receipt-observability',
        delivered_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    events = []
    warnings = []

    def acknowledge(*args, **kwargs):
        if failure is not None:
            raise failure
        return intent

    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'acknowledge_materialization', acknowledge)
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *args, **kwargs: _batch([])
    )
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: events.append(kwargs))),
    )
    monkeypatch.setattr(chat_first_router.logger, 'warning', lambda *args, **kwargs: warnings.append(args))

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(receipts=[{'intent_id': intent.intent_id, 'receipt_id': 'receipt-observability'}]),
    )

    assert response.status_code == 200
    assert {'event': 'kernel_receipt', 'source': 'materialization', 'reason': outcome} in events
    assert bool(warnings) is (outcome in {'conflict', 'generation_mismatch'})
    if warnings:
        assert warnings[0][2:] == (intent.intent_id, 'receipt-observability')


@pytest.mark.parametrize(('stalled_source', 'expected'), [(None, False), ('capture_arrival', True)])
def test_stalled_batch_metric_is_emitted_only_when_source_is_set(monkeypatch, stalled_source, expected):
    _enable_chat_first(monkeypatch)
    events = []
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'fetch_ready_intent_batch',
        lambda *args, **kwargs: _batch([], stalled_source=stalled_source),
    )
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: events.append(kwargs))),
    )

    response = _client().post('/v2/chat/materialize-prompts', json=_request())

    assert response.status_code == 200
    stalled = [event for event in events if event['event'] == 'stalled']
    assert bool(stalled) is expected
    if expected:
        assert stalled == [{'event': 'stalled', 'source': 'capture_arrival', 'reason': 'ready_older_than_24h'}]


def test_one_stale_cold_start_terminal_receipt_never_fails_the_materialization_batch(monkeypatch):
    _enable_chat_first(monkeypatch)
    calls = []

    def acknowledge_terminal(*args, **kwargs):
        calls.append(kwargs['sequence_id'])
        if kwargs['sequence_id'] == 'cold-start:stale':
            raise chat_first_router.chat_first_intents_db.ProactiveIntentNotReady('stale receipt')

    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'acknowledge_sparse_cold_start_sequence_terminal',
        acknowledge_terminal,
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *args, **kwargs: _batch([])
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(
            terminal_receipts=[
                {
                    'sequence_id': 'cold-start:stale',
                    'receipt_id': 'terminal-stale',
                    'terminal_state': 'completed',
                },
                {
                    'sequence_id': 'cold-start:7',
                    'receipt_id': 'terminal-current',
                    'terminal_state': 'completed',
                },
            ]
        ),
    )

    assert response.status_code == 200
    assert calls == ['cold-start:stale', 'cold-start:7']
    assert response.json()['receipt_outcomes'] == [
        {'intent_id': 'cold-start:stale', 'outcome': 'missing'},
        {'intent_id': 'cold-start:7', 'outcome': 'acknowledged'},
    ]


def test_tail_deferral_is_reported_separately_from_rejection(monkeypatch):
    _enable_chat_first(monkeypatch)
    deferrals = []

    def record_deferral(*args, **kwargs):
        deferrals.append(kwargs)
        if kwargs['intent_id'] == 'intent-broken':
            raise RuntimeError('broken deferral')

    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'record_materialization_deferral',
        record_deferral,
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    fetched = []
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'fetch_ready_intent_batch',
        lambda *args, **kwargs: fetched.append(kwargs) or _batch([]),
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(
            deferrals=[
                {'intent_id': 'intent-broken', 'code': 'tail_question'},
                {'intent_id': 'intent-deferred', 'code': 'tail_question'},
            ]
        ),
    )

    assert response.status_code == 200
    assert [item['intent_id'] for item in deferrals] == ['intent-broken', 'intent-deferred']
    assert fetched[0]['deferred_intent_ids'] == {'intent-deferred'}


def test_seven_day_deferral_records_deferred_beyond_budget_metric(monkeypatch):
    _enable_chat_first(monkeypatch)
    dead_lettered = ProactiveIntent(
        intent_id='intent-deferred',
        continuity_key='deferred-seven-days',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='deferred'),
        blocks=[_question()],
        created_at=datetime(2026, 7, 8, tzinfo=timezone.utc),
        delivery_state='dead_letter',
        dead_letter_reason='deferred_beyond_budget',
    )
    events = []
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'record_materialization_deferral',
        lambda *args, **kwargs: dead_lettered,
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *a, **k: _batch([]))
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: events.append(kwargs))),
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(deferrals=[{'intent_id': dead_lettered.intent_id, 'code': 'tail_question'}]),
    )

    assert response.status_code == 200
    assert {'event': 'dead_letter', 'source': 'capture_arrival', 'reason': 'deferred_beyond_budget'} in events


def test_client_rejection_codes_never_create_unbounded_metric_labels(monkeypatch):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-client-code',
        continuity_key='client-code',
        account_generation=7,
        source='capture_arrival',
        subject=None,
        blocks=[_question()],
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    events = []
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'record_materialization_rejection',
        lambda *args, **kwargs: (intent, 'permanent_rejection:invented_client_code'),
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'fetch_ready_intent_batch', lambda *a, **k: _batch([]))
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: SimpleNamespace(inc=lambda: events.append(kwargs))),
    )

    response = _client().post(
        '/v2/chat/materialize-prompts',
        json=_request(rejections=[{'intent_id': intent.intent_id, 'code': 'invented_client_code'}]),
    )

    assert response.status_code == 200
    assert {'event': 'rejected', 'source': 'capture_arrival', 'reason': 'unknown'} in events
    assert {'event': 'dead_letter', 'source': 'capture_arrival', 'reason': 'permanent_rejection:unknown'} in events


def test_v1_leaves_conversation_link_pending_and_v2_later_acknowledges_it(monkeypatch):
    _enable_chat_first(monkeypatch)
    intent = ProactiveIntent(
        intent_id='intent-meeting-1',
        continuity_key='capture:conversation-1',
        account_generation=7,
        source='capture_arrival',
        subject=ChatFirstSubject(kind='capture', id='conversation-1'),
        blocks=[
            ConversationLinkSpec(
                type='conversationLink',
                conversation_id='conversation-1',
                summary='Meeting notes ready',
            )
        ],
        created_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )
    acknowledgements = []
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', _empty_release_batch)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_cold_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_first_router, '_maybe_persist_daily_opener', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'fetch_ready_intent_batch',
        lambda *args, **kwargs: _batch([] if kwargs.get('exclude_block_types') else [intent]),
    )
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'acknowledge_materialization',
        lambda *args, **kwargs: acknowledgements.append(kwargs)
        or intent.model_copy(update={'delivery_state': 'delivered'}),
    )
    projected = []
    monkeypatch.setattr(
        chat_first_router.finalization_jobs_db,
        'mark_meeting_receipt_materialized',
        lambda *args, **kwargs: projected.append((args, kwargs)) or True,
    )
    client = _client()

    legacy = client.post('/v1/chat/materialize-prompts', json=_request())
    modern = client.post('/v2/chat/materialize-prompts', json=_request())
    acknowledged = client.post(
        '/v2/chat/materialize-prompts',
        json=_request(receipts=[{'intent_id': intent.intent_id, 'receipt_id': 'kernel-receipt-1'}]),
    )

    assert legacy.status_code == 200 and legacy.json()['intents'] == []
    assert modern.status_code == 200 and modern.json()['intents'][0]['intent_id'] == intent.intent_id
    assert acknowledged.status_code == 200
    assert len(acknowledgements) == 1
    assert projected[0][0] == ('user-1', 'conversation-1', intent.intent_id)


def test_daily_opener_waits_for_an_active_sparse_cold_start_sequence(monkeypatch):
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'has_active_sparse_cold_start_sequence',
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'has_cold_start_intent_created_on',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('daily lookup must not run')),
    )
    monkeypatch.setattr(
        chat_first_router,
        'persist_daily_opener_intent',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('daily intent must not be created')),
    )

    chat_first_router._maybe_persist_daily_opener(
        'user-1',
        control_generation=7,
        now=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ('handler_name', 'failing_dependency'),
    [
        ('_maybe_persist_daily_opener', 'has_active_sparse_cold_start_sequence'),
        ('_maybe_persist_cold_start', 'get_user_goals'),
    ],
)
def test_preparation_failures_do_not_log_raw_authenticated_uid(monkeypatch, caplog, handler_name, failing_dependency):
    uid = 'sensitive-user-123456'
    if failing_dependency == 'has_active_sparse_cold_start_sequence':
        monkeypatch.setattr(
            chat_first_router.chat_first_intents_db,
            failing_dependency,
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('unavailable')),
        )
    else:
        monkeypatch.setattr(
            chat_first_router.goals_db,
            failing_dependency,
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('unavailable')),
        )

    caplog.set_level(logging.WARNING, logger=chat_first_router.__name__)
    getattr(chat_first_router, handler_name)(
        uid,
        control_generation=7,
        now=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )

    assert uid not in caplog.text
    assert 'error=RuntimeError' in caplog.text


def test_deferral_receiver_is_capability_gated_before_its_store(monkeypatch):
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7, chat_first_ui_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'record_deferral',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('deferral store must not run')),
    )
    monkeypatch.setattr(
        chat_first_router,
        'CHAT_FIRST_PROACTIVE_TOTAL',
        SimpleNamespace(labels=lambda **kwargs: (_ for _ in ()).throw(AssertionError('metric must not run'))),
    )
    question = _question()
    request = {
        'source_surface': 'main_chat',
        'control_generation': 7,
        'owner_fence': 'user-1',
        'continuity_key': 'defer-goal-1',
        'subject': question.subject.model_dump(),
        'question': question.model_dump(),
    }

    response = _client().post('/v1/chat/deferrals', json=request)

    assert response.status_code == 404
