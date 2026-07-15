"""API contracts for the journal-owned materialization fetch/ack boundary."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.chat_first import ChatFirstSubject, ProactiveIntent, QuestionCardSpec, QuestionOption
from models.task_intelligence import TaskWorkflowControl
import routers.chat_first as chat_first_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_first_router.router)
    app.dependency_overrides[chat_first_router.auth.get_current_user_uid] = lambda: 'user-1'
    return TestClient(app)


def _request(*, generation: int = 7, owner_fence: str = 'user-1', receipts=None) -> dict:
    return {
        'source_surface': 'main_chat',
        'control_generation': generation,
        'owner_fence': owner_fence,
        'window_foreground': False,
        'receipts': receipts or [],
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
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )
    for name in ('acknowledge_materialization', 'release_due_deferrals', 'fetch_ready_intents'):
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
        'fetch_ready_intents',
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
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db,
        'acknowledge_materialization',
        lambda *args, **kwargs: acknowledgements.append(kwargs) or intent,
    )
    monkeypatch.setattr(chat_first_router.chat_first_intents_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        chat_first_router.chat_first_intents_db, 'fetch_ready_intents', lambda *args, **kwargs: [intent]
    )

    response = _client().post(
        '/v1/chat/materialize-prompts',
        json=_request(receipts=[{'intent_id': 'intent-1', 'receipt_id': 'kernel-receipt-1'}]),
    )

    assert response.status_code == 200
    assert len(acknowledgements) == 1
    assert acknowledgements[0]['intent_id'] == 'intent-1'
    assert acknowledgements[0]['receipt_id'] == 'kernel-receipt-1'
    assert acknowledgements[0]['account_generation'] == 7
    assert response.json()['intents'][0]['intent_id'] == 'intent-1'
    assert response.json()['intents'][0]['delivery_state'] == 'ready'


def test_deferral_receiver_is_capability_gated_before_its_store(monkeypatch):
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7, chat_first_ui_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
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
