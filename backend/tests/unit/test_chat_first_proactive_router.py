"""Released endpoints cannot manufacture a turn on Chat open."""

from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import database.chat_first_intents as intents_db
from models.task_intelligence import TaskWorkflowControl
import routers.chat_first as chat_first_router


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


@pytest.mark.parametrize('version', ['v1', 'v2'])
@pytest.mark.parametrize('foreground', [False, True])
def test_chat_open_serves_no_daily_cold_start_capture_or_queued_intents(monkeypatch, version, foreground):
    _enable_chat_first(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError('automatic producer store must remain untouched')

    for name in (
        'create_intent',
        'get_or_create_cold_start_intent',
        'fetch_ready_intent_batch',
        'release_due_deferrals',
        'acknowledge_materialization',
        'record_materialization_rejection',
    ):
        monkeypatch.setattr(intents_db, name, forbidden)
    monkeypatch.setattr(chat_first_router.goals_db, 'get_user_goal', forbidden)
    monkeypatch.setattr(chat_first_router.action_items_db, 'get_action_items', forbidden)
    response = _client().post(
        f'/{version}/chat/materialize-prompts', json={**_request(), 'window_foreground': foreground}
    )
    assert response.status_code == 200
    assert response.json()['intents'] == []


def test_retired_deferral_acknowledges_without_scheduling_a_chat_entry(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        intents_db, 'record_deferral', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not persist'))
    )
    body = {
        'source_surface': 'main_chat',
        'control_generation': 7,
        'owner_fence': 'user-1',
        'continuity_key': 'deferral-key',
        'subject': {'kind': 'goal', 'id': 'goal-1'},
        'question': {
            'type': 'questionCard',
            'question_id': 'question-1',
            'text': 'Next?',
            'subject': {'kind': 'goal', 'id': 'goal-1'},
            'options': [{'option_id': 'yes', 'label': 'Yes', 'prepared_answer': 'Yes'}],
        },
    }
    first = _client().post('/v1/chat/deferrals', json=body)
    second = _client().post('/v1/chat/deferrals', json=body)
    assert first.status_code == 200
    assert first.json()['state'] == 'released'
    assert first.json()['deferral_id'] == second.json()['deferral_id']
