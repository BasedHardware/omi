"""Tests for the desktop trial paywall reconnect gate (#7318).

Validates:
- Admission phase rejects paywalled desktop before gauge increment
- No paywall close block inside the session body (removed, handled in admission)
- Cache invalidation on payment/BYOK changes
- is_trial_paywalled handles platform filtering (only desktop/macos affected)
- Behavioral tests for is_trial_paywalled and clear_trial_paywall_cache
"""

from unittest.mock import patch, MagicMock

import pytest

TRANSCRIBE_SRC_PATH = 'routers/transcribe.py'
PAYMENT_SRC_PATH = 'routers/payment.py'
USERS_SRC_PATH = 'routers/users.py'
SUBSCRIPTION_SRC_PATH = 'utils/subscription.py'


def _read_source(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


class TestAdmissionPhase:
    """Verify paywalled desktop users are rejected in the admission phase, before gauge increment."""

    def test_paywall_check_before_gauge_inc(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('is_trial_paywalled(uid, source)')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        assert paywall_pos != -1, "is_trial_paywalled call not found in _stream_handler"
        assert gauge_pos != -1, "gauge inc not found in _stream_handler"
        assert paywall_pos < gauge_pos, "paywall check must come before gauge inc"

    def test_paywall_rejection_returns_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('if is_trial_paywalled(')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        paywall_block = handler_body[paywall_pos:gauge_pos]
        assert 'return' in paywall_block, "paywall rejection must return before gauge inc"

    def test_paywall_close_uses_1008(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('if is_trial_paywalled(')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        paywall_block = handler_body[paywall_pos:gauge_pos]
        assert (
            'websocket.close' in paywall_block and '1008' in paywall_block
        ), "admission paywall must close with code 1008"

    def test_paywall_close_reason_is_trial_expired(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('if is_trial_paywalled(')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        paywall_block = handler_body[paywall_pos:gauge_pos]
        assert 'trial_expired' in paywall_block, "paywall close must use reason 'trial_expired'"

    def test_uid_check_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        uid_check_pos = handler_body.find('Bad uid')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        assert uid_check_pos != -1, "uid check not found in _stream_handler"
        assert gauge_pos != -1, "gauge inc not found in _stream_handler"
        assert uid_check_pos < gauge_pos, "uid check must come before gauge inc"

    def test_freemium_event_sent_before_close(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('if is_trial_paywalled(')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        paywall_block = handler_body[paywall_pos:gauge_pos]
        event_pos = paywall_block.find('FreemiumThresholdReachedEvent')
        close_pos = paywall_block.find('websocket.close')
        assert event_pos != -1, "admission must send FreemiumThresholdReachedEvent for desktop client"
        assert close_pos != -1
        assert event_pos < close_pos, "freemium event must be sent before websocket close"


class TestGaugeIncTryFinally:
    """Verify gauge inc is immediately before the try/finally that decrements it — no leakable returns."""

    def test_inc_immediately_before_try(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        inc_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        try_pos = handler_body.find('try:', inc_pos)
        between = handler_body[inc_pos + len('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()') : try_pos]
        assert 'return' not in between, "no return statements allowed between gauge inc and try block"

    def test_unsupported_language_return_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        lang_pos = handler_body.find('The language is not supported')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        assert lang_pos != -1, "unsupported language check not found"
        assert lang_pos < gauge_pos, "unsupported language return must come before gauge inc"

    def test_bad_user_return_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        user_pos = handler_body.find('Bad user')
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        assert user_pos != -1, "bad user check not found"
        assert user_pos < gauge_pos, "bad user return must come before gauge inc"


class TestNoPaywallBlockInSession:
    """Verify the old paywall close block was removed from inside the session."""

    def test_no_paywalled_desktop_variable(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        after_gauge = handler_body[gauge_pos:]
        assert (
            'is_paywalled_desktop' not in after_gauge
        ), "is_paywalled_desktop variable should not exist after gauge inc — handled in admission"

    def test_no_cooldown_calls(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert 'check_trial_paywall_ws_cooldown' not in src, "cooldown check removed"
        assert 'set_trial_paywall_ws_cooldown' not in src, "cooldown set removed"

    def test_gauge_dec_in_finally(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        finally_pos = handler_body.rfind('finally:')
        assert finally_pos != -1
        finally_block = handler_body[finally_pos:]
        assert 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()' in finally_block, "gauge dec must be in the finally block"


class TestCacheInvalidation:
    """Verify trial paywall cache is cleared on subscription and BYOK changes."""

    def test_clear_trial_paywall_cache_clears_expired_key(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert 'trial_paywall:expired:' in src, "clear function must delete expired cache"
        fn_start = src.find('def clear_trial_paywall_cache')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert 'delete_generic_cache' in fn_body

    def test_payment_clears_paywall_cache_at_all_invalidation_sites(self):
        src = _read_source(PAYMENT_SRC_PATH)
        signal_count = src.count('set_credits_invalidation_signal(uid)')
        clear_count = src.count('clear_trial_paywall_cache(uid)')
        assert signal_count == clear_count, (
            f"payment.py has {signal_count} set_credits_invalidation_signal calls "
            f"but only {clear_count} clear_trial_paywall_cache calls — must match"
        )

    def test_payment_imports_clear_function(self):
        src = _read_source(PAYMENT_SRC_PATH)
        assert (
            'clear_trial_paywall_cache' in src.split('from utils.subscription import')[1].split(')')[0]
        ), "payment.py must import clear_trial_paywall_cache from utils.subscription"

    def test_byok_activate_clears_paywall_cache(self):
        src = _read_source(USERS_SRC_PATH)
        lines = src.split('\n')
        in_activate = False
        found_clear = False
        for line in lines:
            if 'def activate_byok_endpoint' in line:
                in_activate = True
            if in_activate and 'clear_trial_paywall_cache' in line:
                found_clear = True
                break
            if in_activate and line.strip().startswith('def ') and 'activate_byok' not in line:
                break
        assert found_clear, "activate_byok_endpoint must call clear_trial_paywall_cache"

    def test_byok_deactivate_clears_paywall_cache(self):
        src = _read_source(USERS_SRC_PATH)
        lines = src.split('\n')
        in_deactivate = False
        found_clear = False
        for line in lines:
            if 'def deactivate_byok_endpoint' in line:
                in_deactivate = True
            if in_deactivate and 'clear_trial_paywall_cache' in line:
                found_clear = True
                break
            if in_deactivate and line.strip().startswith('def ') and 'deactivate_byok' not in line:
                break
        assert found_clear, "deactivate_byok_endpoint must call clear_trial_paywall_cache"


class TestCacheInvalidationBehavioral:
    """Verify clear_trial_paywall_cache implementation."""

    def test_clear_cache_deletes_expired_key(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def clear_trial_paywall_cache')
        assert fn_start != -1
        fn_end = src.find('\ndef ', fn_start + 1)
        fn_body = src[fn_start:fn_end] if fn_end != -1 else src[fn_start:]
        assert 'delete_generic_cache' in fn_body
        assert 'trial_paywall:expired:' in fn_body
        delete_count = fn_body.count('delete_generic_cache')
        assert (
            delete_count == 1
        ), f"clear_trial_paywall_cache should call delete_generic_cache exactly once, got {delete_count}"


class TestPlatformFiltering:
    """Verify is_trial_paywalled handles platform scoping correctly via source inspection."""

    def test_is_trial_paywalled_checks_desktop_tokens(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert '_TRIAL_PAYWALL_DESKTOP_TOKENS' in src, "must use desktop token set for platform filtering"
        assert 'macos' in src, "desktop tokens must include 'macos'"
        assert 'desktop' in src, "desktop tokens must include 'desktop'"

    def test_is_trial_paywalled_filters_before_expiry_lookup(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        filter_pos = fn_body.find('platform.lower() not in _TRIAL_PAYWALL_DESKTOP_TOKENS')
        expiry_pos = fn_body.find('_is_trial_expired_cached(uid)')
        assert filter_pos != -1, "is_trial_paywalled must filter non-desktop platforms"
        assert expiry_pos != -1, "is_trial_paywalled must call the cached expiry lookup"
        assert filter_pos < expiry_pos, "platform filtering must happen before the expiry lookup"

    def test_is_trial_paywalled_delegates_to_cached_expiry(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert (
            'return _is_trial_expired_cached(uid)' in fn_body
        ), "desktop paywall decisions must use the cached expiry lookup"

    def test_is_trial_paywalled_uses_lower_for_case_insensitivity(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert '.lower()' in fn_body, "is_trial_paywalled must use .lower() for case-insensitive matching"

    def test_admission_calls_is_trial_paywalled_with_source(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        gauge_pos = handler_body.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        admission_body = handler_body[:gauge_pos]
        assert (
            'is_trial_paywalled(uid, source)' in admission_body
        ), "admission phase must call is_trial_paywalled with uid and source"


class TestIsTrialPaywalledBehavioral:
    """Behavioral tests for is_trial_paywalled() — mock internals, test logic directly.

    Uses sys.modules stubs to avoid triggering Firestore/Firebase init on import.
    """

    @pytest.fixture(autouse=True)
    def _setup_subscription(self):
        import sys
        import types

        def _stub(name):
            if name not in sys.modules:
                sys.modules[name] = types.ModuleType(name)
            return sys.modules[name]

        saved = {}
        stubs = [
            'google.cloud',
            'google.cloud.firestore',
            'google.cloud.firestore_v1',
            'firebase_admin',
            'firebase_admin.auth',
            'firebase_admin.firestore',
            'database._client',
            'database.redis_db',
            'database.users',
            'database.user_usage',
            'database.announcements',
        ]
        for name in stubs:
            saved[name] = sys.modules.get(name)
            mod = _stub(name)
            if name == 'database._client':
                mod.db = MagicMock()
            elif name == 'database.redis_db':
                mod.get_generic_cache = MagicMock(return_value=None)
                mod.set_generic_cache = MagicMock()
                mod.delete_generic_cache = MagicMock()
            elif name == 'database.users':
                mod.get_user_valid_subscription = MagicMock(return_value=None)
                mod.is_byok_active = MagicMock(return_value=False)
            elif name == 'database.user_usage':
                pass
            elif name == 'database.announcements':
                mod.compare_versions = MagicMock()
            elif name == 'firebase_admin.auth':
                mock_user = MagicMock()
                mock_user.user_metadata.creation_timestamp = 0
                mod.get_user = MagicMock(return_value=mock_user)

        if 'utils.subscription' in sys.modules:
            del sys.modules['utils.subscription']

        import utils.subscription as sub

        self._sub = sub
        self._mock_expired = MagicMock(return_value=True)
        self._orig_expired = sub._is_trial_expired_cached
        sub._is_trial_expired_cached = self._mock_expired

        yield

        sub._is_trial_expired_cached = self._orig_expired
        for name in stubs:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]

    def test_desktop_expired_returns_true(self):
        assert self._sub.is_trial_paywalled('uid1', 'desktop') is True

    def test_macos_expired_returns_true(self):
        assert self._sub.is_trial_paywalled('uid1', 'macos') is True

    def test_ios_returns_false(self):
        assert self._sub.is_trial_paywalled('uid1', 'ios') is False
        self._mock_expired.assert_not_called()

    def test_android_returns_false(self):
        assert self._sub.is_trial_paywalled('uid1', 'android') is False
        self._mock_expired.assert_not_called()

    def test_none_platform_returns_false(self):
        assert self._sub.is_trial_paywalled('uid1', None) is False
        self._mock_expired.assert_not_called()

    def test_unknown_platform_returns_false(self):
        assert self._sub.is_trial_paywalled('uid1', 'phone_call') is False
        self._mock_expired.assert_not_called()

    def test_mixed_case_desktop(self):
        assert self._sub.is_trial_paywalled('uid1', 'Desktop') is True
        assert self._sub.is_trial_paywalled('uid1', 'MACOS') is True

    def test_desktop_cache_false_returns_false(self):
        self._mock_expired.return_value = False
        assert self._sub.is_trial_paywalled('uid1', 'desktop') is False

    def test_desktop_uid_delegates_to_expiry_cache(self):
        assert self._sub.is_trial_paywalled('uid1', 'desktop') is True
        self._mock_expired.assert_called_with('uid1')

    def test_different_desktop_uid_uses_same_expiry_path(self):
        assert self._sub.is_trial_paywalled('uid99', 'desktop') is True
        self._mock_expired.assert_called_with('uid99')

    def test_not_expired_returns_false(self):
        self._mock_expired.return_value = False
        assert self._sub.is_trial_paywalled('uid1', 'desktop') is False

    def test_clear_cache_calls_redis_delete(self):
        self._sub.clear_trial_paywall_cache('test-uid-123')
        self._sub.redis_db.delete_generic_cache.assert_called_with('trial_paywall:expired:test-uid-123')


class TestByokRequestEscapeHatch:
    """A request carrying all 4 BYOK provider headers must short-circuit the
    trial paywall, even when Firestore says BYOK is inactive (heartbeat expired,
    activation pending, cross-region sync gap).
    """

    @pytest.fixture(autouse=True)
    def _setup_subscription(self):
        import sys
        import types

        def _stub(name):
            if name not in sys.modules:
                sys.modules[name] = types.ModuleType(name)
            return sys.modules[name]

        saved = {}
        stubs = [
            'google.cloud',
            'google.cloud.firestore',
            'google.cloud.firestore_v1',
            'firebase_admin',
            'firebase_admin.auth',
            'firebase_admin.firestore',
            'database._client',
            'database.redis_db',
            'database.users',
            'database.user_usage',
            'database.announcements',
        ]
        for name in stubs:
            saved[name] = sys.modules.get(name)
            mod = _stub(name)
            if name == 'database._client':
                mod.db = MagicMock()
            elif name == 'database.redis_db':
                # Simulate a hot cache that says "expired" — escape hatch must beat it
                mod.get_generic_cache = MagicMock(return_value=True)
                mod.set_generic_cache = MagicMock()
                mod.delete_generic_cache = MagicMock()
            elif name == 'database.users':
                # Firestore says BYOK NOT active — only the request headers should save us
                mod.get_user_valid_subscription = MagicMock(return_value=None)
                mod.is_byok_active = MagicMock(return_value=False)
            elif name == 'database.user_usage':
                pass
            elif name == 'database.announcements':
                mod.compare_versions = MagicMock()
            elif name == 'firebase_admin.auth':
                mock_user = MagicMock()
                mock_user.user_metadata.creation_timestamp = 0
                mod.get_user = MagicMock(return_value=mock_user)

        if 'utils.subscription' in sys.modules:
            del sys.modules['utils.subscription']

        import utils.subscription as sub
        from utils import byok

        self._sub = sub
        self._byok = byok

        yield

        # Reset BYOK contextvar between tests so leftover keys don't bleed.
        byok._byok_ctx.set(None)
        for name in stubs:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]

    def test_all_4_byok_headers_bypass_paywall(self):
        self._byok.set_byok_keys(
            {
                'openai': 'sk-stub-openai',
                'anthropic': 'sk-stub-anthropic',
                'gemini': 'stub-gemini',
                'deepgram': 'stub-deepgram',
            }
        )
        assert self._sub.is_trial_paywalled('uid-stale-firestore', 'desktop') is False

    def test_partial_byok_headers_still_paywall(self):
        # Only 3 of 4 — not a fully-enrolled BYOK request, paywall remains.
        self._byok.set_byok_keys(
            {
                'openai': 'sk-stub',
                'anthropic': 'sk-stub',
                'gemini': 'stub',
                # deepgram missing
            }
        )
        assert self._sub.is_trial_paywalled('uid-stale-firestore', 'desktop') is True

    def test_empty_byok_keys_still_paywall(self):
        self._byok.set_byok_keys({})
        assert self._sub.is_trial_paywalled('uid-stale-firestore', 'desktop') is True

    def test_blank_byok_value_does_not_count(self):
        # A header whose value is empty string shouldn't count as "provided".
        self._byok.set_byok_keys(
            {
                'openai': 'sk-stub',
                'anthropic': 'sk-stub',
                'gemini': 'stub',
                'deepgram': '',
            }
        )
        assert self._sub.is_trial_paywalled('uid-stale-firestore', 'desktop') is True

    def test_get_trial_metadata_byok_headers_not_expired(self):
        self._byok.set_byok_keys(
            {
                'openai': 'sk-stub-openai',
                'anthropic': 'sk-stub-anthropic',
                'gemini': 'stub-gemini',
                'deepgram': 'stub-deepgram',
            }
        )
        meta = self._sub.get_trial_metadata('uid-stale-firestore')
        assert meta.trial_expired is False
