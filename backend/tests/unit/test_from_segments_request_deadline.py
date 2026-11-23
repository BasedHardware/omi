"""The from-segments request deadline bounds the auth wait and the notes step.

The measured 503s sat 123-403 s because the notes step's recovery budget is
agentic 120 s plus one-shot 180 s, and the auth dependency had no bound at all.
The route now sets one request deadline; these tests pin that the auth check and
both notes budgets honour it, and that every other caller is untouched.
"""

import asyncio
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from utils.llm import conversation_processing, notes_agent_policy
from utils.other import endpoints
from routers import developer
from utils.other.raise_site import raise_site_of
from utils.other.request_deadline import (
    FROM_SEGMENTS_REQUEST_BUDGET_SECONDS,
    MINIMUM_DEADLINE_SECONDS,
    RequestDeadlineExceeded,
    call_within_request_deadline,
    capped_deadline_seconds,
    from_segments_request_deadline,
    request_deadline_absolute,
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


# ---------------------------------------------------------------------------
# In-flight auth calls: a single stalled call cannot outlast the budget.
# ---------------------------------------------------------------------------


def test_call_within_request_deadline_runs_inline_without_a_budget():
    assert call_within_request_deadline(lambda: 7) == 7


def test_call_within_request_deadline_does_not_start_a_spent_call():
    started: list[bool] = []
    token = set_request_deadline(0.0)
    try:
        with pytest.raises(RequestDeadlineExceeded):
            call_within_request_deadline(lambda: started.append(True))
    finally:
        reset_request_deadline(token)
    assert started == []


def test_stalled_auth_call_answers_a_retryable_503_within_the_budget(monkeypatch):
    """A hung identity call is abandoned at the budget, not waited out."""
    release = threading.Event()

    def _stalled_verify_token(token: str) -> str:
        release.wait(30)
        raise RuntimeError('released')

    monkeypatch.setattr(endpoints, 'verify_token', _stalled_verify_token)
    token = set_request_deadline(0.5)
    started = time.monotonic()
    try:
        with pytest.raises(HTTPException) as raised:
            endpoints.get_current_user_uid(authorization='Bearer token')
    finally:
        elapsed = time.monotonic() - started
        reset_request_deadline(token)
        release.set()

    assert elapsed < 5.0
    assert raised.value.status_code == 503
    assert raised.value.headers == {'Retry-After': '1'}
    assert raised.value.detail == {'code': 'auth_deadline_exceeded', 'retryable': True}
    assert raise_site_of(raised.value) == 'auth_deadline_exceeded'


def test_auth_chain_still_runs_inline_without_a_budget(monkeypatch):
    """Every other route keeps the existing synchronous auth path."""
    seen: list[str] = []

    def _verify(token: str) -> str:
        seen.append(token)
        return 'uid1'

    monkeypatch.setattr(endpoints, 'verify_token', _verify)
    monkeypatch.setattr(endpoints, 'enforce_account_deletion_http_access', lambda uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda uid, request: None)
    monkeypatch.setattr(endpoints, '_resolve_request_plane_or_503', lambda uid, **kwargs: None)
    monkeypatch.setattr(endpoints, 'validate_byok_request', lambda uid: None)
    monkeypatch.setattr(endpoints, 'record_user_platform', lambda uid, platform: None)
    monkeypatch.setattr(endpoints, 'record_client_device', lambda uid, **kwargs: None)
    monkeypatch.setattr(endpoints, '_recover_locked_content_if_request', lambda uid, request: None)
    monkeypatch.setattr(endpoints, 'load_rollout_cohorts', lambda uid: None)

    assert endpoints.get_current_user_uid(authorization='Bearer token') == 'uid1'
    assert seen == ['token']


# ---------------------------------------------------------------------------
# Notes: one absolute deadline across the agentic attempt and the fallback.
# ---------------------------------------------------------------------------


def _notes_prefix(words: int = 6000):
    from utils.llm.conversation_prompt_context import ConversationPromptPrefix

    return ConversationPromptPrefix(
        conversation_id='conv-deadline',
        context='unused preamble',
        shaped_context=' '.join(['word'] * words),
        has_usable_content=True,
    )


def _notes_kwargs() -> dict:
    return {
        'started_at': datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc),
        'language_code': 'en',
        'output_language_code': 'en',
        'tz': 'UTC',
        'task_intelligence_capture': False,
    }


@pytest.fixture
def shaped_notes(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _passthrough(model):
        yield model

    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')
    monkeypatch.setattr(conversation_processing, 'isolated_notes_model', _passthrough)


def test_agentic_stall_does_not_start_the_one_shot_fallback(monkeypatch, shaped_notes):
    """A spent agentic attempt answers retryably instead of buying a second call."""
    one_shot_calls: list[int] = []

    def _stalled_agentic(**kwargs):
        time.sleep(0.6)
        return None

    class _StalledModel:
        async def ainvoke(self, messages):
            one_shot_calls.append(1)
            await asyncio.sleep(30)
            return SimpleNamespace(content='{}')

    monkeypatch.setattr(conversation_processing, 'agentic_notes_payload', _stalled_agentic)
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *args, **kwargs: _StalledModel())

    token = set_request_deadline(0.5)
    started = time.monotonic()
    try:
        with pytest.raises(RequestDeadlineExceeded):
            conversation_processing.get_conversation_notes(_notes_prefix(), **_notes_kwargs())
    finally:
        elapsed = time.monotonic() - started
        reset_request_deadline(token)

    assert elapsed < 5.0
    assert one_shot_calls == []


def test_one_shot_fallback_spends_only_the_remaining_budget(monkeypatch, shaped_notes):
    """The fallback derives its timeout from the same absolute deadline."""
    one_shot_calls: list[int] = []

    def _fast_agentic(**kwargs):
        time.sleep(1.5)
        return None

    class _StalledModel:
        async def ainvoke(self, messages):
            one_shot_calls.append(1)
            await asyncio.sleep(30)
            return SimpleNamespace(content='{}')

    monkeypatch.setattr(conversation_processing, 'agentic_notes_payload', _fast_agentic)
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *args, **kwargs: _StalledModel())

    token = set_request_deadline(2.0)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError) as raised:
            conversation_processing.get_conversation_notes(_notes_prefix(), **_notes_kwargs())
    finally:
        elapsed = time.monotonic() - started
        reset_request_deadline(token)

    # 1.5 s agentic + the 0.5 s that remained, not a fresh 2 s one-shot budget.
    assert elapsed < 2.6
    assert one_shot_calls == [1]
    assert type(raised.value) is TimeoutError


def test_notes_deadline_maps_to_a_tagged_retryable_503():
    from utils.llm.gateway_error_contract import conversation_processing_http_exception

    exc = conversation_processing_http_exception(RequestDeadlineExceeded('spent'))
    assert exc.status_code == 503
    assert exc.headers == {'Retry-After': '2'}
    assert raise_site_of(exc) == 'notes_deadline_exceeded'


def test_absolute_deadline_is_one_instant_for_every_step():
    token = set_request_deadline(10.0)
    try:
        absolute = request_deadline_absolute()
        assert absolute is not None
        assert request_deadline_remaining_seconds() <= 10.0
        assert request_deadline_absolute() == absolute
    finally:
        reset_request_deadline(token)


def test_agentic_budget_is_re_derived_from_the_absolute_deadline():
    """Packet building must not restart the agent's relative timeout."""
    token = set_request_deadline(10.0)
    try:
        decision = notes_agent_policy.plan_notes_agent(uid='uid1', conversation_id='c1', words=6000)
        assert decision.budget is not None
        planned = decision.budget.deadline_seconds
        assert planned <= 10.0

        tighter = set_request_deadline(2.0)
        try:
            rederived = notes_agent_policy.bounded_budget(decision.budget)
        finally:
            reset_request_deadline(tighter)

        assert rederived.deadline_seconds <= 2.0
        assert rederived.deadline_seconds < planned
        assert rederived.force_submit_after_seconds < rederived.deadline_seconds
    finally:
        reset_request_deadline(token)
