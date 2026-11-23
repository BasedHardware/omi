"""The from-segments request deadline bounds the auth wait and the notes step.

The measured 503s sat 123-403 s because the notes step's recovery budget is
agentic 120 s plus one-shot 180 s, and the auth dependency had no bound at all.
The route now sets one request deadline; these tests pin that the auth check and
both notes budgets honour it, and that every other caller is untouched.
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from utils.llm import conversation_processing, notes_agent_policy
from utils.other import endpoints
from utils.other.raise_site import raise_site_of
from utils.other.request_deadline import (
    FROM_SEGMENTS_REQUEST_BUDGET_SECONDS,
    MINIMUM_DEADLINE_SECONDS,
    capped_deadline_seconds,
    from_segments_request_deadline,
    request_deadline_exceeded,
    request_deadline_remaining_seconds,
    reset_request_deadline,
    set_request_deadline,
)


@pytest.fixture
def budget():
    token = set_request_deadline(FROM_SEGMENTS_REQUEST_BUDGET_SECONDS)
    try:
        yield
    finally:
        reset_request_deadline(token)


def test_unset_budget_changes_nothing():
    assert request_deadline_remaining_seconds() is None
    assert request_deadline_exceeded() is False
    assert capped_deadline_seconds(180.0) == 180.0
    assert conversation_processing.notes_mount().budget.deadline_seconds == (
        conversation_processing.NOTES_LOOP_DEADLINE_SECONDS
    )


def test_budget_caps_the_notes_mount(budget):
    assert capped_deadline_seconds(180.0) <= FROM_SEGMENTS_REQUEST_BUDGET_SECONDS
    assert conversation_processing.notes_mount().budget.deadline_seconds <= FROM_SEGMENTS_REQUEST_BUDGET_SECONDS


def test_budget_caps_the_agentic_notes_budget(budget):
    decision = notes_agent_policy.plan_notes_agent(uid='uid1', conversation_id='c1', words=6000)
    assert decision.run is True
    assert decision.budget is not None
    assert decision.budget.deadline_seconds <= FROM_SEGMENTS_REQUEST_BUDGET_SECONDS
    assert decision.budget.force_submit_after_seconds < decision.budget.deadline_seconds


def test_agentic_budget_is_unchanged_without_a_request_budget():
    decision = notes_agent_policy.plan_notes_agent(uid='uid1', conversation_id='c1', words=6000)
    assert decision.budget is not None
    assert decision.budget.deadline_seconds == notes_agent_policy.DEADLINE_SECONDS
    assert decision.budget.force_submit_after_seconds == notes_agent_policy.FORCE_SUBMIT_AFTER_SECONDS


def test_spent_budget_still_yields_a_usable_deadline():
    token = set_request_deadline(0.0)
    try:
        assert request_deadline_exceeded() is True
        assert capped_deadline_seconds(180.0) == MINIMUM_DEADLINE_SECONDS
    finally:
        reset_request_deadline(token)


def test_auth_deadline_check_is_a_noop_without_a_budget():
    endpoints._enforce_auth_deadline()


def test_auth_deadline_check_raises_a_tagged_retryable_503():
    token = set_request_deadline(0.0)
    try:
        with pytest.raises(HTTPException) as raised:
            endpoints._enforce_auth_deadline()
    finally:
        reset_request_deadline(token)

    exc = raised.value
    assert exc.status_code == 503
    assert exc.headers == {'Retry-After': '1'}
    assert exc.detail == {'code': 'auth_deadline_exceeded', 'retryable': True}
    assert raise_site_of(exc) == 'auth_deadline_exceeded'


def test_dependency_sets_and_resets_the_budget():
    async def run() -> None:
        generator = from_segments_request_deadline()
        await generator.__anext__()
        assert request_deadline_remaining_seconds() is not None
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()
        assert request_deadline_remaining_seconds() is None

    asyncio.run(run())


def test_budget_is_a_ceiling_not_a_floor():
    token = set_request_deadline(5.0)
    try:
        assert capped_deadline_seconds(1.0) == 1.0
        assert capped_deadline_seconds(180.0) <= 5.0
    finally:
        reset_request_deadline(token)


def test_route_resolves_the_deadline_before_the_auth_dependency():
    """The contextvar must be set before get_current_user_uid runs in its thread."""
    from routers import developer

    route = next(
        route for route in developer.router.routes if getattr(route, 'path', None) == '/v1/conversations/from-segments'
    )
    first = route.dependant.dependencies[0]
    assert first.call is from_segments_request_deadline
    assert time.monotonic() > 0


def test_budget_reaches_a_sync_dependency_and_the_sync_handler():
    """FastAPI runs both in a threadpool; the context copy must carry the budget."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    seen: dict[str, float | None] = {}
    app = FastAPI()

    def _sync_dependency() -> None:
        seen['dependency'] = request_deadline_remaining_seconds()

    @app.post('/probe')
    def _probe(_guard: None = Depends(from_segments_request_deadline), _dep: None = Depends(_sync_dependency)):
        seen['handler'] = request_deadline_remaining_seconds()
        return {'ok': True}

    assert TestClient(app).post('/probe').status_code == 200
    assert seen['dependency'] is not None
    assert seen['handler'] is not None
    assert seen['handler'] <= FROM_SEGMENTS_REQUEST_BUDGET_SECONDS
    # The dependency's finally reset it, so the next request starts clean.
    assert request_deadline_remaining_seconds() is None
