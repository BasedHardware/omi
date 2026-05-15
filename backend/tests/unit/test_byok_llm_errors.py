import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

sys.modules.setdefault('database._client', MagicMock())


class _HTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_classify_byok_llm_error_authentication():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("bad api key", 401)) == 'invalid'


def test_classify_byok_llm_error_permission():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("project denied", 403)) == 'permission'


def test_classify_byok_llm_error_insufficient_quota():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("insufficient_quota", 429)) == 'quota'


def test_classify_byok_llm_error_ignores_transient_rate_limit():
    from utils.llm.byok_errors import classify_byok_llm_error

    assert classify_byok_llm_error(_HTTPError("rate limit reached, retry later", 429)) is None


@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_notifies_actionable_byok_error(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
):
    from utils.llm.byok_errors import handle_llm_error

    mock_send_each.return_value = SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    mock_get_tokens.assert_called_once_with('user-1')
    mock_send_each.assert_called_once()
    message = mock_send_each.call_args.args[0][0]
    assert message.data == {'type': 'byok_llm_error', 'provider': 'openai', 'reason': 'quota'}


@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value=None)
def test_handle_llm_error_does_not_notify_platform_error(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_send_each,
):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_not_called()
    mock_send_each.assert_not_called()


def test_validate_byok_request_records_current_uid():
    from utils.byok import get_byok_uid, validate_byok_request

    with patch('utils.byok._check_byok_validity', return_value=None):
        validate_byok_request('user-1')

    assert get_byok_uid() == 'user-1'


def test_anthropic_proxy_constructs_default_client_lazily():
    from utils.llm.clients import _AnthropicClientProxy

    created = []

    def _fake_client(**kwargs):
        created.append(kwargs)
        return object()

    proxy = _AnthropicClientProxy()

    with patch('utils.llm.clients.get_byok_key', return_value=None), patch(
        'utils.llm.clients.anthropic.AsyncAnthropic', side_effect=_fake_client
    ):
        assert created == []
        proxy._resolve()

    assert created == [{'timeout': 120.0, 'max_retries': 1}]
