"""Hermetic cap admission, real ASGI bytes, and pre-write background skip contracts.

No provider/database imports: execute actual source entrypoints with narrow fakes.
"""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import ast
import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    byok = ModuleType('utils.byok')
    byok.get_byok_key = Mock(return_value=None)
    byok.has_validated_byok_keys = Mock(return_value=False)
    byok.get_byok_uid = Mock(return_value='user')
    funded = ModuleType('utils.funded_processing')
    funded.processing_allowed = Mock(return_value=False)
    funded.consent_allows = Mock(return_value=True)
    usage = ModuleType('utils.llm.usage_tracker')
    usage.get_current_context = lambda: None
    with stub_modules({'utils.byok': byok, 'utils.funded_processing': funded, 'utils.llm.usage_tracker': usage}):
        module = load_module_fresh('utils.generated_compute', str(BACKEND / 'utils/generated_compute.py'))
        yield module, funded, byok


def _entrypoint(path, name, namespace, *, legacy=False):
    """Load the real function without importing its cloud/provider dependency graph."""
    tree = ast.parse((BACKEND / path).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    node.returns = None
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
        arg.annotation = None
    node.args.defaults = [ast.Constant(None) for _ in node.args.defaults]
    node.args.kw_defaults = [ast.Constant(None) if x is not None else None for x in node.args.kw_defaults]
    if legacy:
        node.body = [
            n
            for n in node.body
            if not (
                isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == 'require_generated_compute'
            )
        ]
    ast.fix_missing_locations(node)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BACKEND / path), 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize(
    'flags',
    [
        (),
        ('STT_CAP_DISPATCH_ENFORCEMENT',),
        ('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED',),
        ('STT_CAP_DISPATCH_ENFORCEMENT', 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED'),
    ],
)
def test_switches_are_independent_and_off_does_no_reads(gate, monkeypatch, flags):
    module, funded, byok = gate
    for flag in flags:
        monkeypatch.setenv(flag, 'true')
    assert module.generated_compute_allowed('user', 'daily_summary') is (not flags)
    assert funded.processing_allowed.call_count == bool(flags)
    if not flags:
        byok.get_byok_key.assert_not_called()
        byok.has_validated_byok_keys.assert_not_called()
        assert module.generated_compute_allowed(None, 'future_feature')


@pytest.mark.parametrize('tier', ['basic', 'plus', 'operator', 'architect', 'legacy_paid'])
@pytest.mark.parametrize('percent', [80, 99.999, 100, 101])
def test_shared_availability_controls_all_tiers_without_plan_authorization(gate, monkeypatch, tier, percent):
    module, funded, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    funded.processing_allowed.return_value = percent < 100
    # No plan resolver exists in this module. Cap policy is entirely the shared resolver's answer.
    assert module.generated_compute_allowed('user', f'{tier}_feature') == (percent < 100)
    funded.processing_allowed.assert_called_once_with('user')


@pytest.mark.parametrize(
    'validated,keys,provider,owner,allow_byok,allowed',
    [
        (False, {'openai': 'key'}, 'openai', 'user', True, False),
        (True, {'deepgram': 'key'}, None, 'user', True, False),
        (True, {'deepgram': 'key'}, 'deepgram', 'user', True, False),
        (True, {'gemini': 'key'}, 'openai', 'user', True, False),
        (True, {'openai': 'key'}, 'openai', 'other', True, False),
        (True, {'openai': 'key'}, 'openai', 'user', True, True),
        (True, {'gemini': 'key'}, None, 'user', True, True),
        (True, {'openai': 'key'}, None, 'user', False, False),
    ],
)
def test_only_validated_actual_customer_provider_funding_exempts(
    gate, monkeypatch, validated, keys, provider, owner, allow_byok, allowed
):
    module, funded, byok = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    byok.has_validated_byok_keys.return_value = validated
    byok.get_byok_uid.return_value = owner
    byok.get_byok_key.side_effect = keys.get
    assert (
        module.generated_compute_allowed('user', 'app_generator', provider=provider, allow_byok=allow_byok) == allowed
    )
    assert funded.processing_allowed.call_count == (not allowed)


class TitleInput(BaseModel):
    session_id: str
    messages: list[Any]


def _title_client(module, *, legacy=False):
    model = SimpleNamespace(invoke=Mock(return_value=SimpleNamespace(content='A Useful Title')))
    write = Mock()
    namespace = dict(
        require_generated_compute=module.require_generated_compute,
        get_llm=lambda *a, **k: model,
        track_usage=lambda *a: nullcontext(),
        Features=SimpleNamespace(CHAT='chat'),
        chat_db=SimpleNamespace(update_chat_session=write),
        cast=cast,
        Any=Any,
    )
    endpoint = _entrypoint('routers/chat_sessions.py', 'generate_session_title', namespace, legacy=legacy)
    app = FastAPI()

    @app.post('/v2/chat/generate-title')
    def route(data: TitleInput):
        data.messages = [SimpleNamespace(**m) for m in data.messages]
        return endpoint(data, uid='user')

    return TestClient(app), model.invoke, write


def test_flag_off_fastapi_response_bytes_equal_existing_route(gate):
    module, funded, _ = gate
    client, invoke, write = _title_client(module)
    legacy, _, _ = _title_client(module, legacy=True)
    payload = {'session_id': 'session', 'messages': [{'sender': 'human', 'text': 'hello'}]}
    response, old_response = client.post('/v2/chat/generate-title', json=payload), legacy.post(
        '/v2/chat/generate-title', json=payload
    )
    assert (response.status_code, response.content, response.headers['content-type']) == (
        old_response.status_code,
        old_response.content,
        old_response.headers['content-type'],
    )
    assert response.content == b'{"title":"A Useful Title"}'
    invoke.assert_called_once()
    write.assert_called_once_with('user', 'session', title='A Useful Title')
    funded.processing_allowed.assert_not_called()


def test_denied_fastapi_response_is_structured_402_before_model_or_writes(gate, monkeypatch):
    module, _, _ = gate
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    client, invoke, write = _title_client(module)
    response = client.post(
        '/v2/chat/generate-title', json={'session_id': 'session', 'messages': [{'sender': 'human', 'text': 'hello'}]}
    )
    assert response.status_code == 402
    detail = response.json()['detail']
    assert detail['error'] == 'usage_budget_exhausted'
    assert detail['trigger'] == 'usage_budget'
    assert detail['choices'] == ['on_device', 'upgrade']
    assert detail['reset_at'] > 0 and len(detail['period_id']) == 7
    invoke.assert_not_called()
    write.assert_not_called()


def test_new_feature_get_llm_cannot_bypass_uid_or_budget(gate, monkeypatch):
    module, _, byok = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    namespace = dict(
        feature_request_timeout=lambda _: 30,
        _get_model_config=lambda _: ('model', 'openai'),
        is_anthropic_only_feature=lambda _: False,
        is_perplexity_only_feature=lambda _: False,
        _effective_byok_provider=lambda m, p: p,
        is_structured_output_feature=lambda _: False,
        get_byok_profile=lambda: None,
        get_byok_key=byok.get_byok_key,
        _require_client_budget=module.require_current_generated_compute,
    )
    factory = _entrypoint('utils/llm/clients.py', 'get_llm', namespace)
    with pytest.raises(HTTPException) as exc:
        factory('new_future_feature', uid='user')
    assert exc.value.status_code == 402
    assert exc.value.detail['feature'] == 'new_future_feature'
    # A validated identity alone, with no key or allowance, cannot fund a new endpoint.
    byok.get_byok_uid.return_value = None
    with pytest.raises(HTTPException):
        factory('new_future_feature')


@pytest.mark.parametrize(
    'path,name,args,expected',
    [
        (
            'utils/other/notifications.py',
            # The wrapper delegates to the cohort producer; this is the retained
            # legacy budget entrypoint, isolated from all database dependencies.
            '_legacy_generate_and_store_daily_summary',
            ('user', 'date', None, None),
            (None, False, 'usage_budget_exhausted'),
        ),
        ('utils/wrapped/generate_2025.py', 'generate_wrapped_2025', ('user',), None),
        ('utils/apps.py', 'update_personas_async', ('user',), None),
        ('utils/llm/knowledge_graph.py', 'extract_knowledge_from_memory', ('user', 'memory', 'id'), None),
        ('utils/llm/trends.py', 'trends_extractor', ('user', [], []), []),
        ('utils/app_integrations.py', '_process_proactive_notification', ('user', None, {'prompt': 'hello'}), None),
        ('utils/app_integrations.py', 'admit_mentor_evaluation', ('user', []), None),
    ],
)
def test_background_denial_skips_before_any_other_dependency(gate, monkeypatch, path, name, args, expected):
    module, _, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    # No database, lock, progress writer, app mutation or provider exists in this namespace.
    function = _entrypoint(path, name, {'generated_compute_allowed': module.generated_compute_allowed})
    assert function(*args) == expected


def test_onboarding_denial_does_not_take_lenient_answer_fallback(gate, monkeypatch):
    module, _, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    function = _entrypoint(
        'utils/onboarding.py',
        '_ai_check_answer',
        dict(
            generated_compute_allowed=module.generated_compute_allowed,
            generated_compute_configured=module.generated_compute_configured,
            run_blocking=run_blocking,
            db_executor=None,
        ),
    )
    assert asyncio.run(function(SimpleNamespace(uid='user'), 'question', 'two words')) is False


@pytest.mark.parametrize(
    'path,name,async_,args',
    [
        ('routers/apps.py', 'generate_description_endpoint', False, (None,)),
        ('routers/apps.py', 'generate_description_and_emoji_endpoint', False, (None,)),
        ('routers/apps.py', 'generate_sample_prompts_endpoint', True, ()),
        ('routers/apps.py', 'generate_app_endpoint', True, (None,)),
        ('routers/apps.py', 'generate_app_icon_endpoint', True, (None,)),
        ('routers/memories.py', 'extract_memory_log', True, (None,)),
        ('routers/knowledge_graph.py', 'extract_knowledge_graph', True, (None,)),
        ('routers/integrations.py', 'synthesize_connector_data', True, (None,)),
        ('routers/task_recommendations.py', 'get_what_matters_now', False, (None,)),
        ('routers/task_recommendations.py', 'evaluate_what_matters_now', False, (None, None)),
    ],
)
def test_interactive_denial_precedes_fallback_catches_and_side_effects(gate, monkeypatch, path, name, async_, args):
    module, _, _ = gate
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    function = _entrypoint(
        path,
        name,
        dict(
            require_generated_compute=module.require_generated_compute,
            generated_compute_configured=module.generated_compute_configured,
            run_blocking=run_blocking,
            db_executor=None,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        if async_:
            asyncio.run(function(*args, uid='user'))
        else:
            function(*args, uid='user')
    assert exc.value.status_code == 402


def test_legacy_proactive_evaluator_returns_no_advice_at_cap(gate, monkeypatch):
    module, _, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    with module.generated_compute_scope('user'):
        function = _entrypoint(
            'utils/llm/proactive_notification.py',
            'evaluate_proactive_notification',
            dict(
                current_generated_compute_allowed=module.current_generated_compute_allowed,
                ProactiveNotificationResult=lambda **kwargs: kwargs,
            ),
        )
        result = function('User', 'facts', [], '', [], [], 3)
    assert result == {'has_advice': False, 'context_summary': ''}


@pytest.mark.parametrize('feature', ['daily_summary', 'app_generator', 'chat_agent', 'future_feature'])
def test_managed_authorizer_cap_precedes_allowlist_and_plan_fail_open(gate, monkeypatch, feature):
    module, _, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    plan_lookup = Mock(side_effect=AssertionError('plan lookup must not precede funded denial'))
    function = _entrypoint(
        'utils/managed_compute.py',
        '_authorize_omi',
        dict(
            generated_compute_allowed=module.generated_compute_allowed,
            _resolve_plan=plan_lookup,
            _decision=lambda **kwargs: SimpleNamespace(**kwargs),
        ),
    )
    decision = function('user', feature, subscription=None)
    assert decision.allowed is False and decision.reason == 'usage_budget_exhausted'
    plan_lookup.assert_not_called()


@pytest.mark.parametrize('ladder', [False, True])
def test_managed_authorizer_reuses_shared_admission_without_another_monthly_scan(gate, monkeypatch, ladder):
    module, funded, _ = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    if ladder:
        monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    funded.processing_allowed.return_value = True
    monthly = Mock(side_effect=AssertionError('no second projection scan'))
    function = _entrypoint(
        'utils/managed_compute.py',
        '_authorize_omi',
        dict(
            generated_compute_allowed=module.generated_compute_allowed,
            execution_admission_enabled=module.execution_admission_enabled,
            _resolve_plan=lambda *args: ('basic', True),
            _UNRESOLVED=object(),
            _decision=lambda **kwargs: SimpleNamespace(**kwargs),
            PAID_PLAN_TYPES={'paid'},
            _is_free_allowlisted=lambda feature: feature == 'daily_summary',
            ladder_v1=SimpleNamespace(
                feature_allowed=lambda *args: None,
                budget_snapshot=monthly,
                account=lambda *args: {'plan_id': 'basic'},
                policy=SimpleNamespace(budget_enforcement_enabled=lambda: ladder),
            ),
        ),
    )
    decision = function('user', 'app_generator', subscription=None)
    assert decision.allowed is ladder
    assert decision.reason == ('ladder_budget_available' if ladder else 'basic_not_entitled')
    monthly.assert_not_called()


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize('cohort,lanes', [('', 'batch'), ('uid:other', 'batch'), ('all', 'live')])
def test_generated_work_uses_shared_owner_and_batch_scope(gate, monkeypatch, ladder, cohort, lanes):
    module, funded, byok = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    assert module.generated_compute_allowed('user', 'synthetic')
    funded.processing_allowed.assert_not_called()


def test_empty_cohort_does_not_deny_unowned_generated_work(gate, monkeypatch):
    module, funded, byok = gate
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', '')
    assert module.generated_compute_allowed(None, 'synthetic')
    funded.processing_allowed.assert_not_called()
