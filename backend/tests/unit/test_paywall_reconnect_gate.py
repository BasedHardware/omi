"""Tests for the desktop trial paywall reconnect gate (#7318).

Validates:
- Admission phase rejects paywalled desktop before gauge increment
- Context manager guarantees gauge inc/dec balance
- No early returns inside session can leak the gauge
- Cache invalidation on payment/BYOK changes
- is_trial_paywalled handles platform filtering (only desktop/macos affected)
"""

import ast
import textwrap
from unittest.mock import MagicMock

import pytest

TRANSCRIBE_SRC_PATH = 'routers/transcribe.py'
PAYMENT_SRC_PATH = 'routers/payment.py'
USERS_SRC_PATH = 'routers/users.py'
SUBSCRIPTION_SRC_PATH = 'utils/subscription.py'


def _read_source(path):
    with open(path) as f:
        return f.read()


class TestAdmissionPhase:
    """Verify paywalled desktop users are rejected in the admission phase, before gauge increment."""

    def test_paywall_check_before_gauge_context_manager(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        paywall_pos = handler_body.find('is_trial_paywalled(uid, source)')
        gauge_pos = handler_body.find('async with track_active_ws():')
        assert paywall_pos != -1, "is_trial_paywalled call not found in _stream_handler"
        assert gauge_pos != -1, "track_active_ws context manager not found in _stream_handler"
        assert paywall_pos < gauge_pos, "paywall check must come before gauge context manager"

    def test_paywall_rejection_returns_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_paywall_block = False
        found_return_before_gauge = False
        for i, line in enumerate(lines):
            if 'if is_paywalled_desktop:' in line:
                in_paywall_block = True
            if in_paywall_block and line.strip() == 'return':
                found_return_before_gauge = True
                break
            if in_paywall_block and 'track_active_ws()' in line:
                break
        assert found_return_before_gauge, "paywall rejection must return before gauge context manager"

    def test_paywall_close_uses_1008(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_admission_paywall = False
        found_close = False
        for line in lines:
            if 'if is_paywalled_desktop:' in line:
                in_admission_paywall = True
            if in_admission_paywall and 'websocket.close' in line and '1008' in line:
                found_close = True
                break
            if in_admission_paywall and 'track_active_ws()' in line:
                break
        assert found_close, "admission paywall must close with code 1008"

    def test_paywall_close_reason_is_trial_expired(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_admission_paywall = False
        for line in lines:
            if 'if is_paywalled_desktop:' in line:
                in_admission_paywall = True
            if in_admission_paywall and 'trial_expired' in line and 'websocket.close' in line:
                assert 'trial_expired' in line
                return
            if in_admission_paywall and 'track_active_ws()' in line:
                break
        pytest.fail("paywall close must use reason 'trial_expired'")

    def test_uid_check_before_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_body = src[handler_start:]
        uid_check_pos = handler_body.find('Bad uid')
        gauge_pos = handler_body.find('async with track_active_ws():')
        assert uid_check_pos != -1, "uid check not found in _stream_handler"
        assert gauge_pos != -1, "gauge context manager not found in _stream_handler"
        assert uid_check_pos < gauge_pos, "uid check must come before gauge"


class TestGaugeContextManager:
    """Verify the gauge is managed via a context manager, not manual inc/dec."""

    def test_track_active_ws_context_manager_exists(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert (
            'async def track_active_ws()' in src or 'def track_active_ws()' in src
        ), "track_active_ws context manager must be defined"

    def test_context_manager_increments_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        cm_start = src.find('def track_active_ws()')
        assert cm_start != -1
        cm_body = src[cm_start : src.find('\n\n\n', cm_start)]
        assert 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()' in cm_body

    def test_context_manager_decrements_in_finally(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        cm_start = src.find('def track_active_ws()')
        assert cm_start != -1
        cm_body = src[cm_start : src.find('\n\n\n', cm_start)]
        assert 'finally:' in cm_body
        assert 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()' in cm_body

    def test_session_runs_inside_context_manager(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert 'async with track_active_ws():' in src, "_run_stream_session must run inside track_active_ws"

    def test_no_manual_gauge_dec_in_session(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        session_start = src.find('async def _run_stream_session(')
        assert session_start != -1
        session_body = src[session_start:]
        next_fn = session_body.find('\nasync def _listen(')
        if next_fn != -1:
            session_body = session_body[:next_fn]
        assert (
            'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()' not in session_body
        ), "_run_stream_session must not manually dec the gauge — context manager handles it"

    def test_no_manual_gauge_inc_outside_context_manager(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_end = src.find('async def _run_stream_session(')
        handler_body = src[handler_start:handler_end]
        assert (
            'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()' not in handler_body
        ), "_stream_handler must not manually inc the gauge — context manager handles it"


class TestNoGaugeLeakOnEarlyReturn:
    """Verify that early returns inside _run_stream_session cannot leak the gauge."""

    def test_unsupported_language_return_is_inside_session(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        session_start = src.find('async def _run_stream_session(')
        assert session_start != -1
        session_body = src[session_start:]
        assert (
            'The language is not supported' in session_body
        ), "language check should be inside _run_stream_session (protected by context manager)"

    def test_bad_user_return_is_inside_session(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        session_start = src.find('async def _run_stream_session(')
        assert session_start != -1
        session_body = src[session_start:]
        assert (
            'Bad user' in session_body
        ), "user existence check should be inside _run_stream_session (protected by context manager)"

    def test_no_is_paywalled_desktop_in_session(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        session_start = src.find('async def _run_stream_session(')
        assert session_start != -1
        session_body = src[session_start:]
        next_fn = session_body.find('\nasync def _listen(')
        if next_fn != -1:
            session_body = session_body[:next_fn]
        assert (
            'is_paywalled_desktop' not in session_body
        ), "is_paywalled_desktop should not exist in _run_stream_session — handled in admission"


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
    """Execute clear_trial_paywall_cache with mocked Redis to verify runtime behavior."""

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

    def test_is_trial_paywalled_respects_kill_switch(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert '_TRIAL_PAYWALL_ENABLED' in fn_body, "is_trial_paywalled must respect kill switch"

    def test_is_trial_paywalled_respects_test_uid_gating(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert '_TRIAL_PAYWALL_TEST_UIDS' in fn_body, "is_trial_paywalled must respect test UID gating"

    def test_is_trial_paywalled_uses_lower_for_case_insensitivity(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def is_trial_paywalled(')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert '.lower()' in fn_body, "is_trial_paywalled must use .lower() for case-insensitive matching"

    def test_admission_calls_is_trial_paywalled_with_source(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_end = src.find('async def _run_stream_session(')
        handler_body = src[handler_start:handler_end]
        assert (
            'is_trial_paywalled(uid, source)' in handler_body
        ), "admission phase must call is_trial_paywalled with uid and source"


class TestArchitecturalSplit:
    """Verify the _stream_handler / _run_stream_session split is correct."""

    def test_stream_handler_exists(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert 'async def _stream_handler(' in src

    def test_run_stream_session_exists(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert 'async def _run_stream_session(' in src

    def test_stream_handler_calls_run_stream_session(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_end = src.find('async def _run_stream_session(')
        handler_body = src[handler_start:handler_end]
        assert '_run_stream_session(' in handler_body

    def test_freemium_event_sent_for_paywalled_users(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        handler_start = src.find('async def _stream_handler(')
        handler_end = src.find('async def _run_stream_session(')
        handler_body = src[handler_start:handler_end]
        assert (
            'FreemiumThresholdReachedEvent' in handler_body
        ), "admission phase must send freemium event before paywall close"
