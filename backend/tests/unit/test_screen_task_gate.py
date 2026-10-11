"""Screen-gate behavior and its authenticated, OCR-only HTTP boundary."""

import logging

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from routers import desktop_task_gate as route
from utils.llm import screen_task_gate as gate
from utils.llm.jev_client import JevAnswers
from utils.managed_compute import Decision
from utils.rate_limit_config import get_effective_limit
from utils.llm import screen_task_admission as admission
import redis


@pytest.fixture(autouse=True)
def managed_admission(monkeypatch):
    monkeypatch.delenv('SCREEN_TASK_STOP', raising=False)
    monkeypatch.setattr(
        route,
        'authorize_managed_compute',
        lambda *a: Decision(True, 'plan_paid', 'screen_frame_judge', 'omi', None, True),
    )
    monkeypatch.setattr(route, 'check_screen_task_limit', lambda *a: None)


def _answers(score):
    return JevAnswers(None, {'needs_extraction': {'noul': score}})


@pytest.mark.parametrize('score,passed', [(0.49, False), (0.5, True), (0.9, True)])
def test_threshold_is_recall_tuned_and_inclusive(monkeypatch, score, passed):
    monkeypatch.setattr(gate, 'ask_jev', lambda *a, **k: _answers(score))
    decision = gate.decide_screen_task('private screen', audit_draw=1)
    assert decision.should_extract == passed
    assert decision.audit_sample is False


def test_error_passes_without_inventing_a_score(monkeypatch):
    seen = []
    monkeypatch.setattr(gate, 'ask_jev', lambda *a, **k: None)
    monkeypatch.setattr(gate, 'record_fallback', lambda **k: seen.append(k))
    assert gate.decide_screen_task('private screen') == gate.ScreenTaskGateDecision(True, 'fail_open')
    assert seen[0]['outcome'] == 'recovered'


def test_rejected_audit_is_independent_and_configurable(monkeypatch):
    monkeypatch.setattr(gate, 'ask_jev', lambda *a, **k: _answers(0.1))
    assert gate.decide_screen_task('screen', audit_draw=0.009).audit_sample
    assert not gate.decide_screen_task('screen', audit_draw=0.01).should_extract
    monkeypatch.setenv('SCREEN_TASK_JEV_THRESHOLD', '0.05')
    assert gate.decide_screen_task('screen', audit_draw=1).outcome == 'passed'


@pytest.mark.parametrize('value', ['NaN', 'inf', '-1', '2', 'invalid'])
def test_invalid_config_uses_measured_default(monkeypatch, value):
    monkeypatch.setenv('SCREEN_TASK_JEV_THRESHOLD', value)
    monkeypatch.setattr(gate, 'ask_jev', lambda *a, **k: _answers(0.5))
    assert gate.decide_screen_task('screen').should_extract


def test_gateway_deadline_and_lane_are_bounded(monkeypatch):
    seen = []
    monkeypatch.setattr(gate, 'ask_jev', lambda *a, **k: seen.append(k) or _answers(0.5))
    gate.decide_screen_task('screen')
    assert seen == [{'lane': 'screen_task', 'timeout_seconds': 2.0, 'max_attempts': 1}]


@pytest.mark.asyncio
async def test_http_route_rejects_without_pixels_and_logs_only_bounded_fields(monkeypatch, caplog):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.screen_task_gate.__defaults__[0].dependency] = lambda: 'synthetic-user'
    monkeypatch.setattr(route, 'is_desktop_trial_paywalled', lambda *a: False)
    seen = []
    monkeypatch.setattr(
        route, 'decide_screen_task', lambda state: seen.append(state) or gate.ScreenTaskGateDecision(False, 'rejected')
    )
    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
            result = await client.post(
                '/v1/screen-task/gate', json={'ocr_text': 'PRIVATE_SENTINEL', 'related_tasks': ['private task']}
            )
            invalid = await client.post('/v1/screen-task/gate', json={'ocr_text': 'screen', 'image': 'pixels'})
    assert result.json() == {'should_extract': False, 'gate_outcome': 'rejected', 'audit_sample': False}
    assert invalid.status_code == 422
    assert 'PRIVATE_SENTINEL' in seen[0]
    assert 'PRIVATE_SENTINEL' not in caplog.text and 'private task' not in caplog.text


@pytest.mark.asyncio
async def test_http_gate_preserves_trial_paywall(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.screen_task_gate.__defaults__[0].dependency] = lambda: 'synthetic-user'
    monkeypatch.setattr(route, 'is_desktop_trial_paywalled', lambda *a: True)
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('paywalled request called Jev'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        result = await client.post('/v1/screen-task/gate', json={'ocr_text': 'screen'})
    assert result.status_code == 402


@pytest.mark.asyncio
@pytest.mark.parametrize('reason,status', [('basic_not_entitled', 402), ('authorization_unavailable', 503)])
async def test_managed_denial_is_terminal_and_never_calls_provider(monkeypatch, reason, status):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user_uid] = lambda: 'synthetic-user'
    monkeypatch.setattr(
        route, 'authorize_managed_compute', lambda *a: Decision(False, reason, 'screen_frame_judge', 'omi', None, True)
    )
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('denied request spent provider work'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        result = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'})
    assert result.status_code == status
    assert result.headers['X-Omi-Retryable'] == 'false'


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_policy", ["screen_task:gate", "screen_task:gate_daily"])
async def test_gate_has_separate_burst_and_daily_budgets_and_typed_quota(monkeypatch, blocked_policy):
    seen = []

    def limit(uid, policy):
        seen.append((uid, policy))
        if policy == blocked_policy:
            raise HTTPException(429, headers={'Retry-After': '70'})

    monkeypatch.setattr(route, 'check_screen_task_limit', limit)
    monkeypatch.setattr(
        route, 'authorize_managed_compute', lambda *a: pytest.fail('quota request resolved subscription')
    )
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('quota request spent provider work'))
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user_uid] = lambda: 'synthetic-user'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        result = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'})
    assert [p for _, p in seen] == (
        ['screen_task:gate', 'screen_task:gate_daily'] if blocked_policy.endswith('_daily') else ['screen_task:gate']
    )
    assert result.status_code == 429
    assert result.headers['Retry-After'] == '70'
    assert result.json()['detail']['error'] == 'gate_budget_exhausted'
    assert result.headers['X-Omi-Retryable'] == 'false'
    assert get_effective_limit('screen_task:gate', boost=100) == (30, 60)
    assert get_effective_limit('screen_task:gate_daily', boost=100) == (6000, 86400)


@pytest.mark.asyncio
async def test_runtime_stop_is_typed_and_admission_lease_is_bounded(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user_uid] = lambda: 'synthetic-user'
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('stopped request spent provider work'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        before = await client.get('/v1/screen-task/admission')
        monkeypatch.setenv('SCREEN_TASK_STOP', 'true')
        after = await client.get('/v1/screen-task/admission')
        stopped = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'})
    assert before.json() == {'enabled': True, 'lease_seconds': 55}
    assert after.json()['enabled'] is False
    assert stopped.status_code == 409
    assert stopped.json()['detail']['error'] == 'screen_task_stopped'
    assert stopped.headers['X-Omi-Retryable'] == 'false'


def test_gate_budget_fails_closed_on_redis_and_never_obeys_shadow(monkeypatch):
    def unavailable(*args):
        raise redis.exceptions.ConnectionError('synthetic unavailable')

    monkeypatch.setattr(admission, 'check_rate_limit', unavailable)
    with pytest.raises(HTTPException) as caught:
        admission.check_screen_task_limit('synthetic-user', 'screen_task:gate')
    assert caught.value.status_code == 503
    assert caught.value.headers['X-Omi-Retryable'] == 'false'
    monkeypatch.setattr(admission, 'check_rate_limit', lambda *args: (False, 0, 65))
    with pytest.raises(HTTPException) as caught:
        admission.check_screen_task_limit('synthetic-user', 'screen_task:gate')
    assert caught.value.status_code == 429
    assert caught.value.headers['Retry-After'] == '65'


def _gate_app():
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user_uid] = lambda: 'synthetic-user'
    return app


def _serve_gate(monkeypatch):
    monkeypatch.setattr(route, 'is_desktop_trial_paywalled', lambda *a: False)
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: gate.ScreenTaskGateDecision(False, 'rejected'))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'headers,refused',
    [
        ({'user-agent': 'Omi/12433 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'Omi%20Beta/12433 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'Omi%20Beta/12434 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'Omi/12435 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi%20Beta/12435 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/13000 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'x-app-platform': 'macos', 'x-app-build': '12433', 'x-app-version': '0.12.433'}, True),
        ({'x-app-platform': 'macos', 'x-app-build': '12434', 'x-app-version': '0.12.434'}, True),
        ({'x-app-platform': 'macos', 'x-app-build': '12435', 'x-app-version': '0.12.435'}, False),
        ({}, False),
        ({'user-agent': 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36'}, False),
        ({'user-agent': 'Omi-windows/12433'}, False),
        ({'x-app-platform': 'windows', 'user-agent': 'Omi/12433 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/not-a-build CFNetwork/1.0 Darwin/1.0'}, False),
        (
            {
                'user-agent': 'Omi/12435 CFNetwork/1.0 Darwin/1.0',
                'x-app-platform': 'macos',
                'x-app-build': '12433',
                'x-app-version': '0.12.433',
            },
            False,
        ),
    ],
)
async def test_build_floor_refuses_only_identified_old_macos_on_gate_and_admission(monkeypatch, headers, refused):
    monkeypatch.delenv('SCREEN_TASK_MIN_MACOS_BUILD', raising=False)
    if refused:
        monkeypatch.setattr(route, 'check_screen_task_limit', lambda *a: pytest.fail('refused build was admitted'))
        monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('refused build called the provider'))
        monkeypatch.setattr(route, 'authorize_managed_compute', lambda *a: pytest.fail('refused build resolved a plan'))
    else:
        _serve_gate(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(_gate_app()), base_url='http://local') as client:
        gated = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'}, headers=headers)
        admitted = await client.get('/v1/screen-task/admission', headers=headers)
    if refused:
        assert gated.status_code == 409
        assert gated.json()['detail']['error'] == 'screen_task_build_below_floor'
        assert gated.headers['X-Omi-Retryable'] == 'false'
        assert admitted.status_code == 409
        assert admitted.json()['detail']['error'] == 'screen_task_build_below_floor'
        assert admitted.headers['X-Omi-Retryable'] == 'false'
    else:
        assert gated.status_code == 200
        assert gated.json()['gate_outcome'] == 'rejected'
        assert admitted.status_code == 200
        assert admitted.json() == {'enabled': True, 'lease_seconds': 55}


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['nope', '', '0', '-1', '12435.0', 'true', '2147483648'])
async def test_invalid_build_floor_keeps_the_default(monkeypatch, value):
    monkeypatch.setenv('SCREEN_TASK_MIN_MACOS_BUILD', value)
    monkeypatch.setattr(route, 'decide_screen_task', lambda *a: pytest.fail('invalid floor admitted 12434'))
    headers = {'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(_gate_app()), base_url='http://local') as client:
        result = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'}, headers=headers)
    assert result.status_code == 409
    assert result.json()['detail']['error'] == 'screen_task_build_below_floor'


@pytest.mark.asyncio
async def test_build_floor_override_is_read_per_request(monkeypatch):
    headers = {'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'}
    _serve_gate(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(_gate_app()), base_url='http://local') as client:
        monkeypatch.setenv('SCREEN_TASK_MIN_MACOS_BUILD', '12434')
        served = await client.post('/v1/screen-task/gate', json={'ocr_text': 'synthetic'}, headers=headers)
        monkeypatch.setenv('SCREEN_TASK_MIN_MACOS_BUILD', '13000')
        refused = await client.get('/v1/screen-task/admission', headers=headers)
    assert served.status_code == 200
    assert refused.status_code == 409
    assert refused.json()['detail']['error'] == 'screen_task_build_below_floor'


@pytest.mark.asyncio
async def test_build_floor_refusal_log_and_counter_are_bounded(monkeypatch, caplog):
    from utils.llm.screen_task_admission import SCREEN_TASK_BUILD_FLOOR_REFUSALS_TOTAL

    monkeypatch.delenv('SCREEN_TASK_MIN_MACOS_BUILD', raising=False)
    counter = SCREEN_TASK_BUILD_FLOOR_REFUSALS_TOTAL.labels(surface='gate')
    before = counter._value.get()
    headers = {'user-agent': 'Omi/12433 CFNetwork/9.9 Darwin/9.9'}
    with caplog.at_level(logging.INFO, logger='utils.llm.screen_task_admission'):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(_gate_app()), base_url='http://local') as client:
            result = await client.post('/v1/screen-task/gate', json={'ocr_text': 'PRIVATE_SENTINEL'}, headers=headers)
    assert result.status_code == 409
    assert counter._value.get() == before + 1
    assert 'reason=build_below_floor' in caplog.text
    assert 'surface=gate' in caplog.text
    assert 'CFNetwork' not in caplog.text and 'PRIVATE_SENTINEL' not in caplog.text and '12433' not in caplog.text


def test_gate_daily_budget_admits_full_day_at_messaging_cadence_and_retains_burst(monkeypatch):
    from database import redis_db

    clock = [0]
    counters = {}

    def lua(*, keys, args):
        key = keys[0]
        window = args[0]
        count, expiry = counters.get(key, (0, clock[0] + window))
        if expiry <= clock[0]:
            count, expiry = 0, clock[0] + window
        count += 1
        counters[key] = count, expiry
        return count, expiry - clock[0]

    monkeypatch.setattr(redis_db, '_RATE_LIMIT_LUA', lua)
    monkeypatch.setattr(admission, 'check_rate_limit', redis_db.check_rate_limit)
    for frame in range(5760):
        clock[0] = frame * 15
        admission.check_screen_task_limit('synthetic-cadence', 'screen_task:gate')
        admission.check_screen_task_limit('synthetic-cadence', 'screen_task:gate_daily')
    for _ in range(6000 - 5760):
        admission.check_screen_task_limit('synthetic-cadence', 'screen_task:gate_daily')
    with pytest.raises(HTTPException) as daily:
        admission.check_screen_task_limit('synthetic-cadence', 'screen_task:gate_daily')
    assert daily.value.status_code == 429
    for _ in range(30):
        admission.check_screen_task_limit('synthetic-burst', 'screen_task:gate')
    with pytest.raises(HTTPException) as burst:
        admission.check_screen_task_limit('synthetic-burst', 'screen_task:gate')
    assert burst.value.status_code == 429
