"""Screen-gate behavior and its authenticated, OCR-only HTTP boundary."""

import logging

import httpx
import pytest
from fastapi import FastAPI

from routers import desktop_task_gate as route
from utils.llm import screen_task_gate as gate
from utils.llm.jev_client import JevAnswers


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
