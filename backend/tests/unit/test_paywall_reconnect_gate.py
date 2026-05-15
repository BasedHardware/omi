"""Tests for the desktop trial paywall reconnect gate (#7318).

Validates:
- Redis cooldown fast-reject before gauge increment
- Cooldown set on paywall close
- Gauge balance on paywall close path
- Cache invalidation on payment/BYOK changes
- Source filtering (only desktop/macos affected)
"""

import ast
import inspect
import textwrap
from unittest.mock import patch, MagicMock

import pytest

TRANSCRIBE_SRC_PATH = 'routers/transcribe.py'
PAYMENT_SRC_PATH = 'routers/payment.py'
USERS_SRC_PATH = 'routers/users.py'
SUBSCRIPTION_SRC_PATH = 'utils/subscription.py'


def _read_source(path):
    with open(path) as f:
        return f.read()


class TestCooldownGate:
    """Verify the Redis cooldown fast-reject is wired correctly in _stream_handler."""

    def test_cooldown_check_before_gauge_inc(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        cooldown_pos = src.find('check_trial_paywall_ws_cooldown')
        gauge_pos = src.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
        assert cooldown_pos != -1, "cooldown check not found in transcribe.py"
        assert gauge_pos != -1, "gauge inc not found in transcribe.py"
        assert cooldown_pos < gauge_pos, "cooldown check must come before gauge inc"

    def test_cooldown_check_uses_source_filter(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        cooldown_line = None
        for i, line in enumerate(lines):
            if 'check_trial_paywall_ws_cooldown(uid)' in line:
                block = '\n'.join(lines[max(0, i - 3) : i + 1])
                cooldown_line = block
                break
        assert cooldown_line is not None, "cooldown function call not found"
        assert (
            'macos' in cooldown_line or 'desktop' in cooldown_line
        ), "cooldown check must filter by desktop/macos source"

    def test_cooldown_reject_closes_with_1008(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_cooldown_block = False
        found_close = False
        for line in lines:
            if 'check_trial_paywall_ws_cooldown(uid)' in line:
                in_cooldown_block = True
            if in_cooldown_block and 'websocket.close' in line and '1008' in line:
                found_close = True
                break
            if in_cooldown_block and 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS' in line:
                break
        assert found_close, "cooldown reject must close with code 1008"

    def test_cooldown_reason_is_cooldown_specific(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        assert (
            'trial_expired_cooldown' in src
        ), "cooldown close reason must be 'trial_expired_cooldown' (distinct from 'trial_expired')"


class TestPaywallCloseGaugeFix:
    """Verify gauge balance on the paywall close path."""

    def test_paywall_close_sets_cooldown(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        found_set_before_close = False
        for i, line in enumerate(lines):
            if 'set_trial_paywall_ws_cooldown' in line:
                remaining = '\n'.join(lines[i : i + 10])
                if 'trial_expired' in remaining and 'websocket.close' in remaining:
                    found_set_before_close = True
                    break
        assert found_set_before_close, "paywall close path must call set_trial_paywall_ws_cooldown before close"

    def test_paywall_close_decrements_gauge(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_paywall_block = False
        found_dec = False
        for i, line in enumerate(lines):
            if 'is_paywalled_desktop' in line and 'if ' in line:
                in_paywall_block = True
            if in_paywall_block:
                if 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()' in line:
                    found_dec = True
                    break
                if line.strip() == 'return' and found_dec:
                    break
                if line.strip().startswith('# Credit cache') or line.strip().startswith('# Fair-use'):
                    break
        assert found_dec, "paywall close path must decrement the gauge before return"

    def test_gauge_dec_in_finally(self):
        src = _read_source(TRANSCRIBE_SRC_PATH)
        lines = src.split('\n')
        in_paywall_block = False
        found_try = False
        found_finally_dec = False
        for i, line in enumerate(lines):
            if 'is_paywalled_desktop' in line and 'if ' in line:
                in_paywall_block = True
            if in_paywall_block and 'asyncio.sleep(0.5)' in line:
                found_try = True
            if in_paywall_block and found_try and 'finally:' in line:
                next_lines = '\n'.join(lines[i : i + 3])
                if 'BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()' in next_lines:
                    found_finally_dec = True
                break
            if in_paywall_block and 'return' in line and not found_try:
                break
        assert found_finally_dec, "gauge dec on paywall path should be in a finally block"


class TestCacheInvalidation:
    """Verify trial paywall cache is cleared on subscription and BYOK changes."""

    def test_clear_trial_paywall_cache_clears_both_keys(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert 'trial_paywall:expired:' in src, "clear function must delete expired cache"
        assert 'trial_paywall:ws_cooldown:' in src, "clear function must delete cooldown cache"

        fn_start = src.find('def clear_trial_paywall_cache')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert (
            fn_body.count('delete_generic_cache') == 2
        ), "clear_trial_paywall_cache must call delete_generic_cache twice (expired + cooldown)"

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


class TestSubscriptionHelpers:
    """Verify the cooldown/cache helper function logic via source inspection."""

    def test_set_cooldown_uses_correct_key_and_ttl(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def set_trial_paywall_ws_cooldown')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert 'set_generic_cache' in fn_body
        assert 'TRIAL_PAYWALL_WS_COOLDOWN_PREFIX' in fn_body or 'trial_paywall:ws_cooldown:' in fn_body
        assert 'TRIAL_PAYWALL_WS_COOLDOWN_TTL' in fn_body or 'ttl=' in fn_body

    def test_check_cooldown_uses_get_generic_cache(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def check_trial_paywall_ws_cooldown')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert 'get_generic_cache' in fn_body
        assert 'TRIAL_PAYWALL_WS_COOLDOWN_PREFIX' in fn_body or 'trial_paywall:ws_cooldown:' in fn_body

    def test_clear_cache_deletes_both_keys(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        fn_start = src.find('def clear_trial_paywall_cache')
        assert fn_start != -1
        fn_body = src[fn_start : src.find('\ndef ', fn_start + 1)]
        assert fn_body.count('delete_generic_cache') == 2
        assert 'trial_paywall:expired:' in fn_body
        assert 'trial_paywall:ws_cooldown:' in fn_body or 'TRIAL_PAYWALL_WS_COOLDOWN_PREFIX' in fn_body


class TestCooldownTTL:
    """Verify cooldown TTL is reasonable for the reconnect loop scenario."""

    def test_cooldown_ttl_between_30_and_120(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        assert 'TRIAL_PAYWALL_WS_COOLDOWN_TTL = ' in src
        for line in src.split('\n'):
            if 'TRIAL_PAYWALL_WS_COOLDOWN_TTL = ' in line:
                ttl = int(line.split('=')[1].strip())
                assert 30 <= ttl <= 120, f"cooldown TTL {ttl}s should be 30-120s"
                break

    def test_cooldown_ttl_shorter_than_expired_cache_ttl(self):
        src = _read_source(SUBSCRIPTION_SRC_PATH)
        cooldown_ttl = None
        expired_ttl = None
        for line in src.split('\n'):
            if 'TRIAL_PAYWALL_WS_COOLDOWN_TTL = ' in line:
                cooldown_ttl = int(line.split('=')[1].strip())
            if '_TRIAL_PAYWALL_CACHE_TTL_SECONDS = ' in line:
                expired_ttl = int(line.split('=')[1].strip())
        assert cooldown_ttl is not None and expired_ttl is not None
        assert cooldown_ttl < expired_ttl, "cooldown TTL should be shorter than the expired cache TTL"
