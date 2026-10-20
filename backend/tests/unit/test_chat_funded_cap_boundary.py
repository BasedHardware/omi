"""Prepared focused regressions: funded cap must fail before chat stream/persistence.

Execute the actual quota/turn functions against narrow fakes; no cloud/provider IO.
"""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import ast
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]
TIERS = ['basic', 'plus', 'unlimited', 'unlimited_v2', 'operator', 'architect']
RESET_AT = 1793491200


def _load_function(path, name, namespace, *, original=False):
    tree = ast.parse((BACKEND / path).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    node.returns = None
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
        arg.annotation = None
    if original:
        node.body = [
            n
            for n in node.body
            if not (
                isinstance(n, ast.ImportFrom)
                and n.module == 'utils.generated_compute'
                or isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == 'require_generated_compute'
            )
        ]
    ast.fix_missing_locations(node)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BACKEND / path), 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    byok = ModuleType('utils.byok')
    byok.get_byok_key = Mock(return_value=None)
    byok.has_validated_byok_keys = Mock(return_value=False)
    byok.get_byok_uid = Mock(return_value='user')
    funded = ModuleType('utils.funded_processing')
    funded.processing_allowed = Mock(return_value=False)
    funded.consent_allows = Mock(return_value=True)
    with stub_modules({'utils.byok': byok, 'utils.funded_processing': funded}):
        generated = load_module_fresh('utils.generated_compute', str(BACKEND / 'utils/generated_compute.py'))
        plan = SimpleNamespace(value='basic')
        snapshot = {'plan': plan, 'allowed': True, 'unit': 'questions', 'used': 0, 'limit': 30, 'reset_at': RESET_AT}
        namespace = dict(
            Optional=__import__('typing').Optional,
            Any=__import__('typing').Any,
            HTTPException=HTTPException,
            RELEASE_PROBE_UID='omi-release-probe',
            ladder_v1=SimpleNamespace(enforce_chat_budget=Mock(return_value=False)),
            is_trial_paywalled=Mock(return_value=False),
            request_has_byok_provider=lambda provider: byok.get_byok_key(provider),
            _request_has_llm_byok_key=lambda: any(
                byok.get_byok_key(p) for p in ('openai', 'openrouter', 'gemini', 'anthropic')
            ),
            users_db=SimpleNamespace(is_byok_active=Mock(return_value=False)),
            get_chat_quota_snapshot=Mock(return_value=snapshot),
            plan_uses_overage=Mock(return_value=False),
            get_plan_display_name=lambda p: p.value.title(),
            PlanType=SimpleNamespace(basic=plan),
        )
        quota = _load_function('utils/subscription.py', 'enforce_chat_quota', namespace)
        yield SimpleNamespace(
            quota=quota,
            namespace=namespace,
            funded=funded,
            byok=byok,
            generated=generated,
            snapshot=snapshot,
            plan=plan,
        )


def _response_client(quota):
    effects = []
    app = FastAPI()

    @app.post('/chat')
    def route():
        quota('user', platform='desktop')
        effects.append('persist_or_meter')

        def tokens():
            effects.append('provider_stream')
            yield 'data: answer\n\n'

        return StreamingResponse(tokens(), media_type='text/event-stream')

    return TestClient(app), effects


@pytest.mark.parametrize('tier', TIERS)
@pytest.mark.parametrize('overage', [False, True])
def test_stt_only_cap_is_http_402_before_trial_byok_overage_or_stream(boundary, monkeypatch, tier, overage):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    boundary.plan.value = tier
    boundary.namespace['plan_uses_overage'].return_value = overage
    client, effects = _response_client(boundary.quota)
    response = client.post('/chat')
    assert response.status_code == 402
    assert response.headers['content-type'] == 'application/json'
    assert response.json()['detail']['error'] == 'usage_budget_exhausted'
    assert response.json()['detail']['trigger'] == 'usage_budget'
    assert effects == []
    boundary.namespace['is_trial_paywalled'].assert_not_called()
    boundary.namespace['get_chat_quota_snapshot'].assert_not_called()
    boundary.namespace['plan_uses_overage'].assert_not_called()
    boundary.funded.processing_allowed.assert_called_once_with('user')


@pytest.mark.parametrize(
    'allowed,overage,trial', [(True, False, False), (False, False, False), (False, True, False), (False, False, True)]
)
def test_both_off_fastapi_bytes_and_side_effects_match_original_quota(boundary, allowed, overage, trial):
    boundary.snapshot['allowed'] = allowed
    boundary.namespace['plan_uses_overage'].return_value = overage
    boundary.namespace['is_trial_paywalled'].return_value = trial
    original = _load_function('utils/subscription.py', 'enforce_chat_quota', dict(boundary.namespace), original=True)
    old_client, old_effects = _response_client(original)
    client, effects = _response_client(boundary.quota)
    old, response = old_client.post('/chat'), client.post('/chat')
    assert (response.status_code, response.content, response.headers['content-type']) == (
        old.status_code,
        old.content,
        old.headers['content-type'],
    )
    assert effects == old_effects
    boundary.funded.processing_allowed.assert_not_called()
    boundary.byok.has_validated_byok_keys.assert_not_called()


@pytest.mark.parametrize('tier', ['basic', 'plus', 'operator', 'architect'])
def test_ladder_chat_at_cap_detail_is_unchanged_and_precedes_generic_gate(boundary, monkeypatch, tier):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    detail = {
        'error': 'usage_budget_exhausted',
        'trigger': 'usage_budget',
        'chat_at_cap': {'state': 'paused', 'plan_type': tier, 'reset_at': RESET_AT},
    }
    boundary.namespace['ladder_v1'].enforce_chat_budget.side_effect = HTTPException(402, detail)
    client, effects = _response_client(boundary.quota)
    response = client.post('/chat')
    assert response.status_code == 402 and response.json() == {'detail': detail}
    assert effects == []
    boundary.funded.processing_allowed.assert_not_called()
    boundary.byok.has_validated_byok_keys.assert_not_called()


@pytest.mark.parametrize('tier', TIERS)
def test_stt_only_below_cap_keeps_existing_chat_policy(boundary, monkeypatch, tier):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    boundary.plan.value = tier
    boundary.funded.processing_allowed.return_value = True
    boundary.quota('user')
    boundary.namespace['get_chat_quota_snapshot'].assert_called_once()


@pytest.mark.parametrize(
    'validated,provider,key_provider,exempt,allowed',
    [
        (True, 'anthropic', 'anthropic', True, True),
        (False, 'anthropic', 'anthropic', True, False),
        (True, 'anthropic', 'openai', True, False),
        (True, None, 'deepgram', True, False),
        (True, 'anthropic', 'anthropic', False, False),
    ],
)
def test_funded_boundary_uses_validated_provider_funding_and_respects_no_exemption(
    boundary, monkeypatch, validated, provider, key_provider, exempt, allowed
):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    boundary.byok.has_validated_byok_keys.return_value = validated
    boundary.byok.get_byok_key.side_effect = lambda p: 'customer-key' if p == key_provider else None
    boundary.namespace['users_db'].is_byok_active.return_value = True
    if allowed:
        boundary.quota('user', required_llm_provider=provider, byok_exempt=exempt)
    else:
        with pytest.raises(HTTPException) as error:
            boundary.quota('user', required_llm_provider=provider, byok_exempt=exempt)
        assert error.value.status_code == 402
    boundary.namespace['get_chat_quota_snapshot'].assert_not_called()


def test_mobile_turn_propagates_funded_402_before_canned_reply_persistence_or_sse(boundary, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    persist_canned = Mock(side_effect=AssertionError('funded denial must not write a canned reply'))
    resolve_target = Mock(side_effect=AssertionError('funded denial must precede turn preparation'))
    sink = SimpleNamespace(response=Mock(side_effect=AssertionError('no streaming response at funded cap')))
    function = _load_function(
        'utils/chat_turn.py',
        '_run_chat_turn',
        dict(
            enforce_chat_quota=boundary.quota,
            HTTPException=HTTPException,
            surface_runtime=SimpleNamespace(get=lambda: None),
            ReentryEvent=type('ReentryEvent', (), {}),
            _required_chat_quota_provider=lambda: None,
            _build_quota_exceeded_reply=persist_canned,
            resolve_chat_target=resolve_target,
        ),
    )
    options = SimpleNamespace(request=None, plugin_id=None, app_id=None, platform='ios', headers={})
    app = FastAPI()

    @app.post('/v2/messages')
    def route():
        return function(
            'user',
            'app',
            None,
            SimpleNamespace(text='hello'),
            sink,
            principal=SimpleNamespace(authorize=Mock()),
            options=options,
        )

    response = TestClient(app).post('/v2/messages')
    assert response.status_code == 402
    assert response.json()['detail']['error'] == 'usage_budget_exhausted'
    persist_canned.assert_not_called()
    resolve_target.assert_not_called()
    sink.response.assert_not_called()


def test_funded_adapter_import_stays_inside_quota_function():
    tree = ast.parse((BACKEND / 'utils/subscription.py').read_text())
    assert not any(
        isinstance(n, ast.ImportFrom) and n.module in {'utils.generated_compute', 'utils.funded_processing'}
        for n in tree.body
    )
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'enforce_chat_quota')
    assert any(isinstance(n, ast.ImportFrom) and n.module == 'utils.generated_compute' for n in function.body)


def test_release_probe_exemption_cannot_defer_funded_denial_until_stream(boundary, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    with pytest.raises(HTTPException) as error:
        boundary.quota('omi-release-probe')
    assert error.value.status_code == 402
    assert error.value.detail['error'] == 'usage_budget_exhausted'
    boundary.namespace['get_chat_quota_snapshot'].assert_not_called()


def test_release_probe_both_off_retains_question_quota_exemption(boundary):
    boundary.quota('omi-release-probe')
    boundary.namespace['get_chat_quota_snapshot'].assert_not_called()
    boundary.funded.processing_allowed.assert_not_called()
