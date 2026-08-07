"""Regression: POST /v1/apps/enable must not 500 on a malformed setup_completed_url body.

The body of an app's `setup_completed_url` is developer-controlled. When it answered with a
bare JSON scalar (e.g. `true`) the endpoint ran `res.json().get(...)` and raised
AttributeError: 'bool' object has no attribute 'get', turning the intended 400
"App setup is not completed" into an unhandled 500 (~46 prod occurrences 2026-07-21..28).
Non-JSON bodies raised json.JSONDecodeError the same way. No live services.
"""

import os

import httpx

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.app_setup import setup_completed_from_response  # noqa: E402


def _response(content: bytes, content_type: str = "application/json") -> httpx.Response:
    return httpx.Response(200, content=content, headers={"Content-Type": content_type})


def test_object_with_true_flag_is_completed():
    assert setup_completed_from_response(_response(b'{"is_setup_completed": true}')) is True


def test_object_with_false_or_missing_flag_is_not_completed():
    assert setup_completed_from_response(_response(b'{"is_setup_completed": false}')) is False
    assert setup_completed_from_response(_response(b'{}')) is False


def test_bare_json_scalar_is_not_completed():
    # The prod crasher: `res.json()` returns a bool, which has no .get
    assert setup_completed_from_response(_response(b'true')) is False
    assert setup_completed_from_response(_response(b'false')) is False
    assert setup_completed_from_response(_response(b'"ok"')) is False
    assert setup_completed_from_response(_response(b'null')) is False


def test_json_array_is_not_completed():
    assert setup_completed_from_response(_response(b'[{"is_setup_completed": true}]')) is False


def test_non_json_body_is_not_completed():
    assert setup_completed_from_response(_response(b'<html>OK</html>', "text/html")) is False
    assert setup_completed_from_response(_response(b'', "text/plain")) is False
