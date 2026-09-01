"""POST /v1/users/developer/webhook/{wtype} must return 400 (not 500) when 'url' is missing.

set_user_webhook_endpoint read data['url'] via direct subscript, so a body without url raised KeyError ->
500. routers/users.py has a heavy import graph, so we import it under a stub finder and call the handler.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


def _install_python_multipart_stub():
    if 'python_multipart' in sys.modules:
        return False
    if importlib.util.find_spec('python_multipart') is not None:
        return False
    mod = types.ModuleType('python_multipart')
    mod.__version__ = '0.0.20'
    sys.modules['python_multipart'] = mod
    return True


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot_stubbed_modules()
_clear_stubbed_modules()
_rm_mp = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import users as users_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_snap)
    if _rm_mp:
        sys.modules.pop('python_multipart', None)

from fastapi import HTTPException  # noqa: E402
import pydantic  # noqa: E402

from routers.users import SetUserWebhookUrlRequest  # noqa: E402


def _desktop_usage_payload(**overrides):
    today = users_mod.datetime.now(users_mod.pytz.timezone('America/Los_Angeles')).strftime('%Y-%m-%d')
    payload = {
        'date': today,
        'timezone': 'America/Los_Angeles',
        'client_device_id': 'macos_abc123',
        'watching_seconds': 120,
        'listening_seconds': 60,
        'proactive_cards_shown': 3,
        'proactive_cards_acted': 1,
        'ptt_turns': 2,
    }
    payload.update(overrides)
    return payload


def test_desktop_daily_usage_endpoint_records_validated_payload():
    request = users_mod.DesktopDailyUsageRequest.model_validate(_desktop_usage_payload())

    with patch.object(users_mod.daily_summaries_db, 'upsert_desktop_daily_usage') as upsert:
        response = users_mod.record_desktop_daily_usage(request, uid='uid1')

    assert response == {'ok': True}
    upsert.assert_called_once_with(
        'uid1',
        _desktop_usage_payload()['date'],
        'America/Los_Angeles',
        'macos_abc123',
        {
            'watching_seconds': 120,
            'listening_seconds': 60,
            'proactive_cards_shown': 3,
            'proactive_cards_acted': 1,
            'ptt_turns': 2,
        },
    )


@pytest.mark.parametrize(
    'override',
    [
        {'date': '2026-02-30'},
        {'date': '2000-01-01'},
        {'timezone': 'Mars/Olympus_Mons'},
        {'client_device_id': '   '},
        {'client_device_id': 'x' * 201},
        {'watching_seconds': -1},
        {'listening_seconds': 86401},
        {'proactive_cards_shown': 10001},
        {'ptt_turns': True},
    ],
)
def test_desktop_daily_usage_endpoint_rejects_invalid_payload(override):
    with pytest.raises(pydantic.ValidationError):
        users_mod.DesktopDailyUsageRequest.model_validate(_desktop_usage_payload(**override))


def test_daily_summary_day_stats_serializes_new_fields():
    response = users_mod.DailySummaryResponse.model_validate(
        {
            'id': 'summary-1',
            'stats': {
                'total_conversations': 2,
                'total_duration_minutes': 18,
                'action_items_count': 1,
                'memories_created': 3,
                'action_items_created': 4,
                'watching_minutes': 5,
                'proactive_moments': 6,
            },
        }
    )

    assert response.model_dump()['stats'] == {
        'total_conversations': 2,
        'total_duration_minutes': 18,
        'action_items_count': 1,
        'memories_created': 3,
        'action_items_created': 4,
        'watching_minutes': 5,
        'proactive_moments': 6,
    }


def test_missing_url_returns_422():
    # Pydantic rejects missing required field; FastAPI surfaces as 422 at API layer.
    with pytest.raises(pydantic.ValidationError):
        SetUserWebhookUrlRequest()


def test_valid_url_sets():
    with (
        patch.object(users_mod, 'set_user_webhook_db') as setdb,
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success') as reset_health,
    ):
        result = users_mod.set_user_webhook_endpoint(
            wtype='audio_bytes', data=SetUserWebhookUrlRequest(url='http://x'), uid='u1'
        )
    assert result['status'] == 'ok'
    setdb.assert_called_once()
    enable.assert_called_once_with('u1', 'audio_bytes')
    reset_health.assert_called_once_with('u1', 'audio_bytes')
    disable.assert_not_called()


def test_empty_url_disables_without_resetting_health():
    with (
        patch.object(users_mod, 'set_user_webhook_db') as setdb,
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success') as reset_health,
    ):
        result = users_mod.set_user_webhook_endpoint(
            wtype='audio_bytes', data=SetUserWebhookUrlRequest(url=''), uid='u1'
        )
    assert result['status'] == 'ok'
    disable.assert_called_once_with('u1', 'audio_bytes')
    setdb.assert_called_once_with('u1', 'audio_bytes', '')
    enable.assert_not_called()
    reset_health.assert_not_called()


def test_cleared_audio_bytes_url_keeping_delay_disables():
    """#11365: the app posts '<url>,<seconds>', so clearing the URL sends ',5' — not ''.

    That is neither '' nor ',', so the endpoint used to re-enable the webhook the user had
    just switched off, and the toggle came back on after every save.
    """
    with (
        patch.object(users_mod, 'set_user_webhook_db') as setdb,
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success') as reset_health,
    ):
        result = users_mod.set_user_webhook_endpoint(
            wtype='audio_bytes', data=SetUserWebhookUrlRequest(url=',5'), uid='u1'
        )
    assert result['status'] == 'ok'
    disable.assert_called_once_with('u1', 'audio_bytes')
    setdb.assert_called_once_with('u1', 'audio_bytes', ',5')
    enable.assert_not_called()
    reset_health.assert_not_called()


def test_audio_bytes_url_with_delay_still_enables():
    with (
        patch.object(users_mod, 'set_user_webhook_db'),
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success'),
    ):
        users_mod.set_user_webhook_endpoint(
            wtype='audio_bytes', data=SetUserWebhookUrlRequest(url='http://x,5'), uid='u1'
        )
    enable.assert_called_once_with('u1', 'audio_bytes')
    disable.assert_not_called()


def test_blank_url_disables_for_non_audio_webhooks():
    with (
        patch.object(users_mod, 'set_user_webhook_db'),
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success'),
    ):
        users_mod.set_user_webhook_endpoint(wtype='memory_created', data=SetUserWebhookUrlRequest(url='   '), uid='u1')
    disable.assert_called_once_with('u1', 'memory_created')
    enable.assert_not_called()


def test_comma_in_non_audio_url_is_not_a_delay_separator():
    """Only audio_bytes encodes a ',<seconds>' suffix; a query string may contain commas."""
    with (
        patch.object(users_mod, 'set_user_webhook_db'),
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
        patch.object(users_mod, 'record_dev_webhook_success'),
    ):
        users_mod.set_user_webhook_endpoint(
            wtype='realtime_transcript', data=SetUserWebhookUrlRequest(url='https://h/i?ids=1,2'), uid='u1'
        )
    enable.assert_called_once_with('u1', 'realtime_transcript')
    disable.assert_not_called()


def test_get_missing_webhook_url_validates_as_nullable_response():
    with patch.object(users_mod, 'get_user_webhook_db', return_value=None):
        result = users_mod.get_user_webhook_endpoint(wtype='audio_bytes', uid='u1')

    assert result == {'url': None}
    assert users_mod.UserWebhookUrlResponse.model_validate(result).url is None
