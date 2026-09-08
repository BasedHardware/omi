"""Tests for BYOK security fixes (issue #6880).

Covers: Enrollment, subscription entitlements, middleware validation, cache routing, cache invalidation.
"""

import hashlib
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from tests.unit._byok_fixtures import _SHA256_HEX_RE
from tests.unit._byok_fixtures import _byok_isolation  # noqa: F401

# ---------------------------------------------------------------------------
# 10. BYOK activation endpoint validation
# ---------------------------------------------------------------------------


class TestBYOKActivationValidation:
    """Test the actual activate_byok_endpoint and its production constants."""

    def _valid_fingerprints(self) -> Dict[str, str]:
        return {
            'openai': hashlib.sha256(b'sk-openai').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-anthropic').hexdigest(),
            'gemini': hashlib.sha256(b'sk-gemini').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-deepgram').hexdigest(),
        }

    @patch('routers.users.users_db')
    def test_valid_activation_persists_fingerprints(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        data = BYOKActivateRequest(fingerprints=fps)
        result = activate_byok_endpoint(data, uid='test-uid')
        assert result == {"active": True}
        mock_users_db.set_byok_active.assert_called_once_with('test-uid', fps)

    def test_stt_only_activation_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        data = BYOKActivateRequest(fingerprints={'deepgram': hashlib.sha256(b'dg').hexdigest()})
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400
        assert 'LLM' in str(exc_info.value.detail)

    @patch('routers.users.users_db')
    def test_openrouter_only_activation_persists_fingerprint(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fingerprints = {'openrouter': hashlib.sha256(b'or-key').hexdigest()}
        assert activate_byok_endpoint(BYOKActivateRequest(fingerprints=fingerprints), uid='test-uid') == {
            "active": True
        }
        mock_users_db.set_byok_active.assert_called_once_with('test-uid', fingerprints)

    def test_unknown_provider_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['unknown_provider'] = hashlib.sha256(b'x').hexdigest()
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400
        assert 'Unknown provider' in str(exc_info.value.detail)

    def test_63_char_fingerprint_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 63
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    @patch('routers.users.users_db')
    def test_64_char_valid_hex_passes(self, mock_users_db):
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 64
        data = BYOKActivateRequest(fingerprints=fps)
        result = activate_byok_endpoint(data, uid='test-uid')
        assert result == {"active": True}

    def test_65_char_fingerprint_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        fps = self._valid_fingerprints()
        fps['openai'] = 'a' * 65
        data = BYOKActivateRequest(fingerprints=fps)
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    def test_empty_fingerprints_rejects(self):
        from fastapi import HTTPException
        from routers.users import BYOKActivateRequest, activate_byok_endpoint

        data = BYOKActivateRequest(fingerprints={})
        with pytest.raises(HTTPException) as exc_info:
            activate_byok_endpoint(data, uid='test-uid')
        assert exc_info.value.status_code == 400

    @patch('routers.users.users_db')
    def test_deactivation_calls_clear(self, mock_users_db):
        from routers.users import deactivate_byok_endpoint

        result = deactivate_byok_endpoint(uid='test-uid')
        assert result == {"active": False}
        mock_users_db.clear_byok_active.assert_called_once_with('test-uid')

    def test_production_constants_match(self):
        """Verify the test regex matches the production regex."""
        from routers.users import _BYOK_ALLOWED_PROVIDERS as prod_providers, _SHA256_HEX_RE as prod_re

        assert prod_re.pattern == _SHA256_HEX_RE.pattern
        assert prod_providers == {'openai', 'anthropic', 'gemini', 'openrouter', 'deepgram'}


class TestBYOKSubscriptionEntitlements:
    def test_llm_only_byok_keeps_the_transcription_limit(self, monkeypatch):
        from models.users import PlanLimits, PlanType, Subscription
        from routers import users

        subscription = Subscription(plan=PlanType.basic)
        monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
        monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: False)
        monkeypatch.setattr(users, 'get_user_subscription', lambda _uid: subscription, raising=False)
        monkeypatch.setattr(users, 'reconcile_basic_plan_with_stripe', lambda _uid, _subscription: None)
        monkeypatch.setattr(users, 'get_user_valid_subscription', lambda _uid: subscription, raising=False)
        monkeypatch.setattr(
            users,
            'get_plan_limits',
            lambda _plan: PlanLimits(transcription_seconds=37, words_transcribed=50, insights_gained=3),
        )
        monkeypatch.setattr(users, 'get_plan_features', lambda _plan, simplified: [])
        monkeypatch.setattr(users, 'should_show_new_plans', lambda _platform, _version: True)
        monkeypatch.setattr(users, 'get_monthly_usage_for_subscription', lambda _uid: {})
        monkeypatch.setattr(users, 'get_paid_plan_definitions', lambda: [])
        monkeypatch.setattr(users, 'has_ever_purchased', lambda _uid, _subscription: False, raising=False)
        monkeypatch.setattr(users, 'filter_plans_for_user', lambda _definitions, _plan, **_kwargs: [])
        monkeypatch.setattr(users, 'should_hide_subscription_ui', lambda _uid, _platform, _version: False)
        monkeypatch.setattr(
            users,
            'get_phone_call_quota_snapshot',
            lambda _uid: MagicMock(to_client_dict=lambda: {'has_access': False, 'is_paid': False}),
        )
        monkeypatch.setattr(
            users,
            'get_chat_quota_snapshot',
            lambda _uid, platform: {'used': 0, 'unit': 'questions', 'limit': 30, 'allowed': True, 'reset_at': None},
        )
        monkeypatch.setattr(users, 'neo_grandfather_until', lambda _subscription: None)
        monkeypatch.setattr(users, 'wire_plan_for_client', lambda plan, _platform, _version: plan)

        response = users.get_user_subscription_endpoint(uid='llm-byok-user')

        assert response.subscription.plan == PlanType.basic
        assert response.transcription_seconds_limit == 37

    def test_validated_llm_byok_gets_unlimited_subscription(self, monkeypatch):
        from models.users import PlanType
        from routers import users

        monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
        monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: True)

        response = users.get_user_subscription_endpoint(uid='validated-byok-user')

        assert response.subscription.plan == PlanType.unlimited
        assert response.subscription.features == ['byok']

    def test_validated_deepgram_only_does_not_unlock_chat_unlimited(self, monkeypatch):
        from models.users import PlanLimits, PlanType, Subscription
        from routers import users

        subscription = Subscription(plan=PlanType.basic)
        monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
        monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: False)
        monkeypatch.setattr(users, 'get_user_subscription', lambda _uid: subscription, raising=False)
        monkeypatch.setattr(users, 'reconcile_basic_plan_with_stripe', lambda _uid, _subscription: None)
        monkeypatch.setattr(users, 'get_user_valid_subscription', lambda _uid: subscription, raising=False)
        monkeypatch.setattr(
            users,
            'get_plan_limits',
            lambda _plan: PlanLimits(transcription_seconds=37, words_transcribed=50, insights_gained=3),
        )
        monkeypatch.setattr(users, 'get_plan_features', lambda _plan, simplified: [])
        monkeypatch.setattr(users, 'should_show_new_plans', lambda _platform, _version: True)
        monkeypatch.setattr(users, 'get_monthly_usage_for_subscription', lambda _uid: {})
        monkeypatch.setattr(users, 'get_paid_plan_definitions', lambda: [])
        monkeypatch.setattr(users, 'has_ever_purchased', lambda _uid, _subscription: False, raising=False)
        monkeypatch.setattr(users, 'filter_plans_for_user', lambda _definitions, _plan, **_kwargs: [])
        monkeypatch.setattr(users, 'should_hide_subscription_ui', lambda _uid, _platform, _version: False)
        monkeypatch.setattr(
            users,
            'get_phone_call_quota_snapshot',
            lambda _uid: MagicMock(to_client_dict=lambda: {'has_access': False, 'is_paid': False}),
        )
        monkeypatch.setattr(
            users,
            'get_chat_quota_snapshot',
            lambda _uid, platform: {'used': 0, 'unit': 'questions', 'limit': 30, 'allowed': True, 'reset_at': None},
        )
        monkeypatch.setattr(users, 'neo_grandfather_until', lambda _subscription: None)
        monkeypatch.setattr(users, 'wire_plan_for_client', lambda plan, _platform, _version: plan)

        response = users.get_user_subscription_endpoint(uid='deepgram-only-user')

        assert response.subscription.plan == PlanType.basic
        assert response.transcription_seconds_limit == 37

    def test_usage_quota_requires_validated_llm_capability(self, monkeypatch):
        from models.users import PlanType
        from routers import users

        monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
        monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: False)
        monkeypatch.setattr(
            users,
            'get_chat_quota_snapshot',
            lambda _uid, platform=None, **_kwargs: {
                'plan': PlanType.basic,
                'used': 4,
                'unit': 'questions',
                'limit': 30,
                'allowed': True,
                'reset_at': None,
            },
        )

        response = users.get_user_chat_usage_quota(uid='deepgram-only-user')
        assert response.plan_type == PlanType.basic.value
        assert response.limit == 30

        monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: True)
        response = users.get_user_chat_usage_quota(uid='llm-byok-user')
        assert response.plan_type == PlanType.unlimited.value
        assert response.limit is None
        assert response.allowed is True


class TestRequestHasLLMByokKey:
    def test_accepts_openrouter_and_gemini(self, monkeypatch):
        from utils import subscription

        keys = {'openrouter': 'or-key'}
        monkeypatch.setattr(subscription, 'has_validated_byok_keys', lambda: True)
        monkeypatch.setattr(subscription, 'get_byok_uid', lambda: 'uid-1')

        def _enrolled(keys):
            monkeypatch.setattr(
                subscription, 'get_cached_byok_state', lambda _uid: {'fingerprints': {p: 'fp' for p in keys}}
            )
            monkeypatch.setattr(subscription, 'get_byok_key', lambda provider: keys.get(provider))

        _enrolled({'openrouter': 'or-key'})
        assert subscription.request_has_llm_byok_key() is True
        _enrolled({'gemini': 'gm-key'})
        assert subscription.request_has_llm_byok_key() is True
        _enrolled({'deepgram': 'dg-key'})
        assert subscription.request_has_llm_byok_key() is False

    def test_requires_validated_context(self, monkeypatch):
        from utils import subscription

        cached_state = MagicMock(return_value={'fingerprints': {'openai': 'openai-fp'}})
        get_key = MagicMock(return_value='sk')
        monkeypatch.setattr(subscription, 'has_validated_byok_keys', lambda: False)
        monkeypatch.setattr(subscription, 'get_byok_uid', lambda: 'uid-1')
        monkeypatch.setattr(subscription, 'get_cached_byok_state', cached_state)
        monkeypatch.setattr(subscription, 'get_byok_key', get_key)
        assert subscription.request_has_llm_byok_key() is False
        cached_state.assert_not_called()
        get_key.assert_not_called()

    def test_quota_snapshot_accepts_required_llm_provider(self, monkeypatch):
        from models.users import PlanType
        from utils import subscription

        monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *args, **kwargs: False)
        monkeypatch.setattr(subscription.users_db, 'get_user_valid_subscription', lambda *args, **kwargs: None)
        monkeypatch.setattr(
            subscription.user_usage_db,
            'get_monthly_chat_usage',
            lambda *args, **kwargs: {'questions': 1, 'cost_usd': 0.0, 'reset_at': None},
        )
        snapshot = subscription.get_chat_quota_snapshot('uid', required_llm_provider='anthropic')
        assert snapshot['plan'] == PlanType.basic
        assert snapshot['unit'] == 'questions'


class TestBYOKMiddlewareValidation:
    @staticmethod
    def _request(headers, path='/v1/test'):
        from starlette.requests import Request

        return Request(
            {
                'type': 'http',
                'method': 'GET',
                'path': path,
                'headers': [(key.lower().encode(), value.encode()) for key, value in headers.items()],
                'query_string': b'',
                'scheme': 'http',
                'server': ('testserver', 80),
                'client': ('testclient', 1234),
                'http_version': '1.1',
            }
        )

    def test_validated_keys_survive_async_middleware_boundary(self, monkeypatch):
        from utils.byok import BYOKMiddleware, get_byok_keys, has_validated_byok_keys

        async def run_blocking(_executor, function, *args):
            if function.__name__ == 'verify_token':
                return 'middleware-user'
            if function.__name__ == '_validated_byok_keys':
                return args[1], None
            return function(*args)

        monkeypatch.setattr('utils.byok.run_blocking', run_blocking)
        middleware = BYOKMiddleware(MagicMock())
        request = self._request({'Authorization': 'Bearer token', 'X-BYOK-OpenAI': 'sk-valid'})

        async def call_next(_request):
            assert has_validated_byok_keys()
            assert get_byok_keys() == {'openai': 'sk-valid'}
            return 'ok'

        assert __import__('asyncio').run(middleware.dispatch(request, call_next)) == 'ok'

    def test_mismatched_keys_are_rejected_before_route(self, monkeypatch):
        from utils.byok import BYOKMiddleware

        async def run_blocking(_executor, function, *args):
            if function.__name__ == 'verify_token':
                return 'middleware-user'
            return {}, 'BYOK key fingerprint mismatch for provider: openai'

        monkeypatch.setattr('utils.byok.run_blocking', run_blocking)
        middleware = BYOKMiddleware(MagicMock())
        request = self._request({'Authorization': 'Bearer token', 'X-BYOK-OpenAI': 'sk-invalid'})
        called = False

        async def call_next(_request):
            nonlocal called
            called = True
            return 'unreachable'

        response = __import__('asyncio').run(middleware.dispatch(request, call_next))

        assert response.status_code == 403
        assert not called

    def test_mismatched_keys_reach_byok_recovery_routes_without_keys(self, monkeypatch):
        from utils.byok import BYOKMiddleware, get_byok_keys

        async def run_blocking(_executor, function, *args):
            if function.__name__ == 'verify_token':
                return 'middleware-user'
            return {}, 'BYOK key fingerprint mismatch for provider: openai'

        monkeypatch.setattr('utils.byok.run_blocking', run_blocking)
        middleware = BYOKMiddleware(MagicMock())
        request = self._request(
            {'Authorization': 'Bearer token', 'X-BYOK-OpenAI': 'sk-invalid'},
            path='/v1/users/me/subscription',
        )

        async def call_next(_request):
            assert get_byok_keys() == {}
            return 'recovery'

        assert __import__('asyncio').run(middleware.dispatch(request, call_next)) == 'recovery'


# ---------------------------------------------------------------------------
# 11. Cache routing: raw keys never in cache keys
# ---------------------------------------------------------------------------


class TestCacheRouting:
    @staticmethod
    def _stub_openai_constructor(monkeypatch):
        from utils.llm import clients

        class _StubChatOpenAI:
            def __init__(self, **kwargs):
                self.model_name = kwargs['model']
                self.openai_api_base = kwargs.get('base_url')

        constructor = MagicMock(side_effect=_StubChatOpenAI)
        clients._openai_cache.clear()
        monkeypatch.setattr(clients, 'ChatOpenAI', constructor)
        return clients, _StubChatOpenAI, constructor

    def test_cached_openai_chat_no_raw_key_in_cache(self, monkeypatch):
        from utils.llm import clients

        api_key = 'sk-secret-openai-key-for-cache-test'
        monkeypatch.setattr(clients, 'ChatOpenAI', MagicMock())
        clients._cached_openai_chat('gpt-4.1-mini', api_key, {})
        for k in clients._openai_cache.keys():
            assert api_key not in k, f"Raw API key found in cache key: {k}"

    def test_cached_openai_chat_returns_same_instance(self, monkeypatch):
        from utils.llm import clients

        api_key = 'sk-deterministic-test-key'
        fake_client = MagicMock()
        constructor = MagicMock(return_value=fake_client)
        monkeypatch.setattr(clients, 'ChatOpenAI', constructor)

        inst1 = clients._cached_openai_chat('gpt-4.1-mini', api_key, {})
        inst2 = clients._cached_openai_chat('gpt-4.1-mini', api_key, {})

        assert inst1 is inst2
        constructor.assert_called_once_with(model='gpt-4.1-mini', api_key=api_key)

    def test_cached_anthropic_no_raw_key_in_cache(self):
        from utils.llm.clients import _anthropic_cache, _cached_anthropic

        api_key = 'sk-ant-secret-key-for-cache-test'
        _cached_anthropic(api_key)
        for k in _anthropic_cache.keys():
            assert api_key not in k, f"Raw API key found in cache key: {k}"

    def test_cached_anthropic_returns_same_instance(self):
        from utils.llm.clients import _cached_anthropic

        api_key = 'sk-ant-deterministic-key'
        inst1 = _cached_anthropic(api_key)
        inst2 = _cached_anthropic(api_key)
        assert inst1 is inst2

    def test_gemini_byok_routes_to_gemini_endpoint(self, monkeypatch):
        from utils.llm.clients import _GEMINI_OPENAI_BASE_URL

        clients, stub_client, _constructor = self._stub_openai_constructor(monkeypatch)

        client = clients._create_byok_client('gemini-2.5-flash-lite', 'gemini', 'AIza-byok-key')
        assert isinstance(client, stub_client)
        assert client.openai_api_base == _GEMINI_OPENAI_BASE_URL

    def test_openai_byok_creates_client(self, monkeypatch):
        clients, stub_client, _constructor = self._stub_openai_constructor(monkeypatch)

        client = clients._create_byok_client('gpt-4.1-mini', 'openai', 'sk-byok-test-key')
        assert isinstance(client, stub_client)
        assert client.model_name == 'gpt-4.1-mini'

    def test_anthropic_byok_routes_generic_features_through_the_user_key(self, monkeypatch):
        from utils.llm import clients

        client = MagicMock()
        create_client = MagicMock(return_value=client)
        monkeypatch.setattr(clients, '_cached_anthropic_chat', create_client)
        monkeypatch.setattr(
            clients, 'get_byok_key', lambda provider: 'sk-ant-user-key' if provider == 'anthropic' else None
        )
        monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
        monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **kwargs: kwargs['legacy_model'])

        assert clients.get_llm('memories') is client
        create_client.assert_called_once()
        assert create_client.call_args.args[:2] == ('claude-sonnet-4-6', 'sk-ant-user-key')
        assert create_client.call_args.args[2]['timeout'] == 120
        assert 'request_timeout' not in create_client.call_args.args[2]

    def test_anthropic_byok_strips_openai_stream_options(self, monkeypatch):
        """ChatAnthropic must not receive OpenAI-only stream_options, even streaming."""
        from utils.llm import clients

        client = MagicMock()
        create_client = MagicMock(return_value=client)
        monkeypatch.setattr(clients, '_cached_anthropic_chat', create_client)
        monkeypatch.setattr(
            clients, 'get_byok_key', lambda provider: 'sk-ant-user-key' if provider == 'anthropic' else None
        )
        monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
        monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **kwargs: kwargs['legacy_model'])

        assert clients.get_llm('memories', streaming=True) is client
        create_client.assert_called_once()
        ctor_kwargs = create_client.call_args.args[2]
        assert 'stream_options' not in ctor_kwargs
        assert ctor_kwargs['streaming'] is True

    def test_openrouter_gemini_byok_routes_through_openrouter(self, monkeypatch):
        """OpenRouter BYOK keeps Gemini models on the OpenRouter endpoint."""

        clients, stub_client, _constructor = self._stub_openai_constructor(monkeypatch)

        client = clients._create_byok_client('gemini-3-flash-preview', 'openrouter', 'AIza-byok-key')
        assert isinstance(client, stub_client)
        # Must use OpenRouter's compatible endpoint.
        assert client.openai_api_base == 'https://openrouter.ai/api/v1'
        # OpenRouter requires its Google model namespace.
        assert client.model_name == 'google/gemini-3-flash-preview'

    def test_non_gemini_openrouter_creates_client(self):
        """OpenRouter BYOK supports non-Gemini models through its compatible API."""
        from utils.llm.clients import _create_byok_client

        result = _create_byok_client('anthropic/claude-3.5-sonnet', 'openrouter', 'sk-or-key')
        assert result is not None

    def test_legacy_openai_key_never_pairs_with_gemini_resolved_model(self, monkeypatch):
        """A legacy OpenAI key must not be paired with a Gemini-resolved model.

        'followup' resolves to a Gemini model in the BYOK QoS profile. When only a
        legacy OpenAI key is present (no Gemini key), the fallback must select the
        OpenAI-compatible fallback model — never hand the OpenAI credential to the
        resolved Gemini model, which would be an incompatible model/provider
        request at the provider.
        """
        from utils.llm import clients

        create_client = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(clients, '_create_byok_client', create_client)
        # Only a legacy Gemini-resolved feature, but only an OpenAI key is attached.
        monkeypatch.setattr(
            clients, 'get_byok_key', lambda provider: 'sk-legacy-openai' if provider == 'openai' else None
        )
        monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
        monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **kwargs: kwargs['legacy_model'])

        assert clients.get_llm('followup') is not None
        args = create_client.call_args.args
        assert args[0] == 'gpt-4o-mini', f"model must be OpenAI fallback, got {args[0]}"
        assert args[1] == 'openai', f"provider must stay openai, got {args[1]}"
        assert args[2] == 'sk-legacy-openai'

    def test_byok_profile_takes_precedence_over_openrouter_fallback(self, monkeypatch):
        """Profile-specific BYOK route wins over OpenRouter preference.

        'followup' has a Gemini BYOK QoS profile entry. When the user has
        BOTH an OpenRouter key AND a Gemini key, the Gemini profile route
        must be used — OpenRouter must not hijack the feature-specific route.
        """
        from utils.llm import clients

        create_client = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(clients, '_create_byok_client', create_client)
        monkeypatch.setattr(
            clients,
            'get_byok_key',
            lambda provider: (
                'sk-or-key' if provider == 'openrouter' else ('AIza-gemini-key' if provider == 'gemini' else None)
            ),
        )
        monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
        monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **kwargs: kwargs['legacy_model'])

        assert clients.get_llm('followup') is not None
        args = create_client.call_args.args
        assert 'gemini' in args[0], f"model must be Gemini, got {args[0]}"
        assert args[1] == 'gemini', f"provider must be gemini, got {args[1]}"
        assert args[2] == 'AIza-gemini-key', f"key must be Gemini BYOK key, got {args[2]}"


# ---------------------------------------------------------------------------
# 18. Activation cache invalidation
# ---------------------------------------------------------------------------


class TestActivationCacheInvalidation:
    """Verify activate/deactivate endpoints invalidate BYOK state cache."""

    @patch('routers.users.invalidate_byok_state_cache')
    @patch('routers.users.users_db')
    def test_activate_invalidates_cache(self, mock_users_db, mock_invalidate):
        from routers.users import activate_byok_endpoint, BYOKActivateRequest

        fingerprints = {
            'openai': hashlib.sha256(b'sk-o').hexdigest(),
            'anthropic': hashlib.sha256(b'sk-a').hexdigest(),
            'gemini': hashlib.sha256(b'sk-g').hexdigest(),
            'deepgram': hashlib.sha256(b'sk-d').hexdigest(),
        }
        data = BYOKActivateRequest(fingerprints=fingerprints)
        result = activate_byok_endpoint(data=data, uid='uid-act')
        assert result == {'active': True}
        mock_invalidate.assert_called_once_with('uid-act')

    @patch('routers.users.invalidate_byok_state_cache')
    @patch('routers.users.users_db')
    def test_deactivate_invalidates_cache(self, mock_users_db, mock_invalidate):
        from routers.users import deactivate_byok_endpoint

        result = deactivate_byok_endpoint(uid='uid-deact')
        assert result == {'active': False}
        mock_invalidate.assert_called_once_with('uid-deact')
