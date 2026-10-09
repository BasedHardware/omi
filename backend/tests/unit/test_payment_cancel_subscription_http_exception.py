"""Subscription cancellation endpoints must re-raise HTTPException rather than masking as 500.

In routers/payment.py, cancel_app_subscription and cancel_subscription_endpoint explicitly raise
HTTPException with specific status codes (e.g. 404 for missing app subscription or invalid data,
and 400 for missing customer ID). Because HTTPException inherits from Exception, a generic
`except Exception as e:` catch-all without a preceding `except HTTPException: raise` swalllows
these intended client errors and masks them as internal server errors (500), breaking the API
contract and polluting server logs with false-positive alerts.

These tests verify that:
1. Expected HTTPException client errors (404, 400) propagate cleanly to the caller.
2. The source structure in routers/payment.py includes explicit `except HTTPException: raise`
   guards before generic `except Exception` blocks in both cancellation endpoints, matching
   upgrade_subscription_endpoint.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import routers.payment as payment  # noqa: E402

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / 'routers' / 'payment.py'


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding='utf-8')


def test_cancel_app_subscription_reraises_404_when_subscription_not_found():
    with patch('routers.payment.find_app_subscription', return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            payment.cancel_app_subscription('test_app_id', 'test_uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Active subscription not found for this app'


def test_cancel_app_subscription_reraises_404_when_subscription_data_invalid():
    with patch('routers.payment.find_app_subscription', return_value={'id': None}):
        with pytest.raises(HTTPException) as exc_info:
            payment.cancel_app_subscription('test_app_id', 'test_uid')
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Invalid subscription data'


def test_cancel_subscription_endpoint_reraises_400_when_customer_id_missing():
    mock_sub = MagicMock()
    mock_sub.stripe_subscription_id = 'sub_123'
    with (
        patch('routers.payment.users_db.get_user_subscription', return_value=mock_sub),
        patch('routers.payment.users_db.set_user_cancellation_feedback'),
        patch('routers.payment.stripe.Subscription.retrieve', return_value={'customer': None}),
    ):
        with pytest.raises(HTTPException) as exc_info:
            payment.cancel_subscription_endpoint(payment.CancelSubscriptionRequest(), uid='test_uid')
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == 'No customer ID found for subscription.'


def test_cancel_app_subscription_source_has_http_exception_reraise():
    source = _source()
    start = source.index('def cancel_app_subscription(')
    end = source.index('\n@router.', start + 1) if '\n@router.' in source[start + 1 :] else len(source)
    func_source = source[start:end]

    assert 'except HTTPException:\n        raise' in func_source
    http_pos = func_source.index('except HTTPException:')
    generic_pos = func_source.index('except Exception as e:')
    assert http_pos < generic_pos, 'except HTTPException must precede generic except Exception'


def test_cancel_subscription_endpoint_source_has_http_exception_reraise():
    source = _source()
    start = source.index('def cancel_subscription_endpoint(')
    end = source.index('\n@router.', start + 1) if '\n@router.' in source[start + 1 :] else len(source)
    func_source = source[start:end]

    assert 'except HTTPException:\n        raise' in func_source
    http_pos = func_source.index('except HTTPException:')
    generic_pos = func_source.index('except Exception as e:')
    assert http_pos < generic_pos, 'except HTTPException must precede generic except Exception'
