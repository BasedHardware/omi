"""App/persona multipart JSON form contract tests."""

import pytest
from fastapi import HTTPException

from utils.request_validation import parse_form_json


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
