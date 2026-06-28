"""App/persona multipart JSON form contract tests."""

import pytest
from fastapi import HTTPException

from utils.request_validation import (
    backfill_app_home_url_from_auth_steps,
    normalize_required_webhook_url,
    parse_form_json,
)


def test_create_app_invalid_json_returns_422_before_handler_io():
    with pytest.raises(HTTPException) as exc_info:
        parse_form_json(dict, 'this is not json', 'app_data')

    assert exc_info.value.status_code == 422
    assert 'app_data' in exc_info.value.detail


@pytest.mark.parametrize('payload', ['[1, 2, 3]', '"a string"', '42'])
def test_create_app_non_object_json_returns_422_before_handler_io(payload):
    with pytest.raises(HTTPException) as exc_info:
        parse_form_json(dict, payload, 'app_data')

    assert exc_info.value.status_code == 422
    assert 'app_data' in exc_info.value.detail


@pytest.mark.parametrize('webhook_url', ['', '   ', None, 123])
def test_trigger_webhook_url_must_be_nonblank_string(webhook_url):
    external_integration = {'webhook_url': webhook_url}

    with pytest.raises(HTTPException) as exc_info:
        normalize_required_webhook_url(external_integration)

    assert exc_info.value.status_code == 422


def test_trigger_webhook_url_is_trimmed_after_validation():
    external_integration = {'webhook_url': '  https://example.com/webhook  '}

    normalize_required_webhook_url(external_integration)

    assert external_integration['webhook_url'] == 'https://example.com/webhook'


@pytest.mark.parametrize('auth_steps', ['not-a-list', {'url': 'https://example.com'}, [None], ['bad'], [{}]])
def test_auth_steps_app_home_backfill_rejects_malformed_single_step(auth_steps):
    external_integration = {'auth_steps': auth_steps}

    with pytest.raises(HTTPException) as exc_info:
        backfill_app_home_url_from_auth_steps(external_integration)

    assert exc_info.value.status_code == 422


def test_auth_steps_app_home_backfill_accepts_single_url_step():
    external_integration = {'auth_steps': [{'url': 'https://example.com/oauth'}]}

    backfill_app_home_url_from_auth_steps(external_integration)

    assert external_integration['app_home_url'] == 'https://example.com/oauth'
