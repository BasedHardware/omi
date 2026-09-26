"""An auto-disabled app must be recoverable, and a redirect must not disable one.

`POST /v1/apps/enable` refuses any app carrying a stored `disabled` flag. Nothing
about that check is live: it makes no outbound call, so an app disabled months
earlier still fails instantly with copy claiming a current connectivity problem.

Two defects met there. Webhook delivery pins the destination IP and therefore
cannot follow redirects, and every non-2xx — a 3xx included — advanced the 72h
auto-disable clock, so an endpoint that merely redirected was switched off as if
its host were down. And the only branch that clears the flag
(`routers/apps.py`, `disabled is False` on an unset-exclusive payload) is
unreachable from every shipped client, so nothing that landed in that state ever
left it: 202 apps auto-disabled in production, 0 ever recovered, 122 of them
with a host that answered.

Covers the redirect path, the notify-don't-disable response, the re-enable
health check agreeing with delivery, and the install refusal telling the truth.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from database.webhook_health import (
    ACTION_DISABLE,
    ACTION_NONE,
    ACTION_REDIRECT_NOT_FOLLOWED,
    clear_app_webhook_health,
    record_app_webhook_failure,
)
from models.app import App
from routers.apps import _disabled_app_install_detail
from utils.apps import validate_app_endpoints_for_reenable


def _app(**overrides) -> App:
    base = {
        'id': 'app-1',
        'name': 'Test App',
        'image': 'https://example.com/app.png',
        'author': 'Test Author',
        'uid': 'owner-uid',
        'email': 'dev@example.com',
        'category': 'productivity-and-organization',
        'description': 'test app',
        'capabilities': {'external_integration'},
        'deleted': False,
    }
    base.update(overrides)
    return App(**base)


class TestRedirectDoesNotAdvanceAutoDisable:
    """A 3xx means the host answered, so it must never reach the disable clock."""

    @pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
    def test_redirect_never_runs_the_failure_script(self, status):
        script = MagicMock(return_value=ACTION_DISABLE)
        with patch('database.webhook_health._get_failure_script', return_value=script), patch(
            'database.webhook_health.r'
        ) as redis:
            redis.set.return_value = True
            action = record_app_webhook_failure('app-1', status, f'HTTP {status}')

        script.assert_not_called()
        assert action == ACTION_REDIRECT_NOT_FOLLOWED

    def test_redirect_never_marks_the_app_disabled(self):
        with patch('database.webhook_health._get_failure_script', return_value=MagicMock(return_value=3)), patch(
            'database.webhook_health.r'
        ) as redis:
            redis.set.return_value = True
            record_app_webhook_failure('app-1', 307, 'HTTP 307')

        # setex is how the disable path latches `app_webhook_disabled:<id>`.
        redis.setex.assert_not_called()

    def test_repeat_redirects_notify_once_per_interval(self):
        with patch('database.webhook_health.r') as redis:
            redis.set.return_value = None  # NX lost: a notice is already live
            action = record_app_webhook_failure('app-1', 307, 'HTTP 307')
        assert action == ACTION_NONE

    def test_redirect_redis_failure_is_not_an_outage_signal(self):
        with patch('database.webhook_health.r') as redis:
            redis.hset.side_effect = RuntimeError('redis down')
            action = record_app_webhook_failure('app-1', 307, 'HTTP 307')
        assert action == ACTION_NONE

    @pytest.mark.parametrize('status', [500, 502, 404, 401])
    def test_non_redirect_failures_still_reach_the_clock(self, status):
        script = MagicMock(return_value=ACTION_DISABLE)
        with patch('database.webhook_health._get_failure_script', return_value=script), patch(
            'database.webhook_health.r'
        ):
            action = record_app_webhook_failure('app-1', status, f'HTTP {status}')

        script.assert_called_once()
        assert action == ACTION_DISABLE

    def test_re_enable_clears_the_redirect_notice(self):
        with patch('database.webhook_health.r') as redis:
            clear_app_webhook_health('app-1')
        deleted = set(redis.delete.call_args[0])
        assert 'app_webhook_redirect_notice:app-1:realtime' in deleted, (
            'a stale notice key would suppress the next redirect warning for up to a day '
            'after the developer re-enabled'
        )


class TestActionCodeStubsMatchTheRealModule:
    """Two suites hand-stub `database.webhook_health` and must mirror these codes.

    `utils.app_integrations` imports the action codes by name, so a stub missing
    one fails the whole module import — which is how adding them broke
    test_async_app_integrations.py in CI. Hardcoded stub values can also drift
    the other way and silently assert against the wrong number, so this is a
    **static checker**: it reads the stub sources and compares their literals to
    the real module.
    """

    STUBS = (
        "test_async_app_integrations.py",
        "test_async_realtime_integrations_offload.py",
    )

    @pytest.mark.parametrize('stub', STUBS)
    def test_stub_action_codes_match(self, stub):
        import pathlib
        import re

        import database.webhook_health as real

        source = (pathlib.Path(__file__).parent / stub).read_text()
        declared = re.findall(
            r'sys\.modules\["database\.webhook_health"\]\.(ACTION_\w+) = (\d+)',
            source,
        )
        assert declared, f'{stub} no longer stubs the action codes; app_integrations imports them by name'
        for name, value in declared:
            assert getattr(real, name) == int(value), (
                f'{stub} stubs {name}={value} but database.webhook_health defines '
                f'{getattr(real, name)}; the stub would assert against the wrong code'
            )


class TestRedirectNotifiesWithoutDisabling:
    def test_action_notifies_the_owner_and_leaves_the_app_enabled(self):
        import utils.app_integrations as integrations

        with patch.object(integrations, '_notify_app_owner') as notify, patch.object(
            integrations, 'disable_app_in_firestore'
        ) as disable:
            integrations._handle_webhook_health_action('app-1', ACTION_REDIRECT_NOT_FOLLOWED, 'HTTP 307')

        disable.assert_not_called()
        notify.assert_called_once()
        body = notify.call_args[0][2]
        assert 'redirect' in body.lower()
        assert 'not delivered' in body.lower()


class TestReEnableHealthCheckMatchesDelivery:
    """The check must fail whatever delivery would fail, or it green-lights a re-break."""

    def test_health_check_does_not_follow_redirects(self):
        app = {'external_integration': {'webhook_url': 'https://dev.example.com/omi/webhook'}}
        with patch('utils.apps.httpx.request', return_value=httpx.Response(200)) as request:
            validate_app_endpoints_for_reenable(app, {}, 'app-1')

        assert request.call_args.kwargs['follow_redirects'] is False, (
            'delivery pins the destination IP and cannot follow redirects; checking with them '
            'followed passes endpoints that fail on the first real webhook'
        )

    def test_redirecting_webhook_is_rejected_with_an_actionable_reason(self):
        app = {'external_integration': {'webhook_url': 'https://dev.example.com/omi/webhook'}}
        with patch('utils.apps.httpx.request', return_value=httpx.Response(307)):
            with pytest.raises(HTTPException) as exc:
                validate_app_endpoints_for_reenable(app, {}, 'app-1')

        assert exc.value.status_code == 400
        assert 'redirect' in exc.value.detail.lower()

    def test_healthy_webhook_still_passes(self):
        app = {'external_integration': {'webhook_url': 'https://dev.example.com/omi/webhook'}}
        with patch('utils.apps.httpx.request', return_value=httpx.Response(200)):
            validate_app_endpoints_for_reenable(app, {}, 'app-1')

    def test_redirecting_mcp_server_is_rejected(self):
        app = {'external_integration': {'mcp_server_url': 'https://mcp.example.com/mcp'}}
        with patch('utils.apps.httpx.request', return_value=httpx.Response(307)):
            with pytest.raises(HTTPException) as exc:
                validate_app_endpoints_for_reenable(app, {}, 'app-1')

        assert exc.value.status_code == 400
        assert 'redirect' in exc.value.detail.lower()


class TestBlockedInstallExplainsItself:
    def test_owner_is_told_what_to_fix_and_how_to_recover(self):
        app = _app(disabled=True, disabled_reason='webhook_failures', disabled_at='2026-05-30T16:06:32+00:00')
        detail = _disabled_app_install_detail(app, 'owner-uid')

        assert 'Re-enable' in detail, 'the owner must be pointed at the control that actually clears the flag'
        assert '2026-05-30' in detail, 'a months-old disable must not read as a live outage'

    def test_owner_sees_the_recorded_error(self):
        app = _app(disabled=True, disabled_error='HTTP 307', disabled_at='2026-05-30T16:06:32+00:00')
        assert 'HTTP 307' in _disabled_app_install_detail(app, 'owner-uid')

    def test_no_longer_claims_a_live_connectivity_check(self):
        app = _app(disabled=True, disabled_reason='webhook_failures', disabled_at='2026-05-30T16:06:32+00:00')
        for uid in ('owner-uid', 'someone-else'):
            detail = _disabled_app_install_detail(app, uid)
            assert 'connectivity issues' not in detail.lower(), (
                'no connectivity check runs here — the flag is read from the app document, which '
                'sent developers hunting through their own healthy server logs'
            )

    def test_non_owner_is_not_told_to_press_a_control_they_do_not_have(self):
        app = _app(disabled=True, disabled_reason='webhook_failures')
        detail = _disabled_app_install_detail(app, 'someone-else')
        assert 'Re-enable' not in detail
        assert 'developer' in detail.lower()

    def test_app_disabled_before_these_fields_existed_still_reads_sensibly(self):
        # Documents written by the original auto-disable carry no disabled_at/_error.
        app = _app(disabled=True, disabled_reason='webhook_failures')
        detail = _disabled_app_install_detail(app, 'owner-uid')
        assert 'None' not in detail
        assert detail.strip().endswith('.')
