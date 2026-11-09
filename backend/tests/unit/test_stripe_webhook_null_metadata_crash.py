"""Deterministic reproduction test for Stripe webhook NoneType chained lookup crash.

In routers/payment.py, `_handle_stripe_event` accesses `session.get('metadata', {}).get(...)`
and `subscription_obj.get('metadata', {}).get(...)`. When Stripe webhook payloads contain
`"metadata": None` (or null in JSON), Python's `dict.get('metadata', {})` returns `None`
instead of the default `{}` because the `'metadata'` key exists with value `None`.
Consequently, the chained `.get('app_id')` / `.get('uid')` fails with:
`AttributeError: 'NoneType' object has no attribute 'get'`.

This crashes the /v1/payments/stripe/webhook receiver with HTTP 500 on realistic Stripe payloads.
"""

import os
from unittest.mock import patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest
from routers.payment import _handle_stripe_event


@pytest.mark.asyncio
async def test_checkout_session_completed_handles_null_metadata_gracefully():
    """A checkout.session.completed event with metadata=None must not raise AttributeError."""
    event = {
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': 'cs_test_null_metadata',
                'client_reference_id': None,
                'metadata': None,
            }
        },
    }

    # In unpatched code, session.get('metadata', {}).get('app_id') raises AttributeError
    result = await _handle_stripe_event(event)
    assert result == {'status': 'success'}


@pytest.mark.asyncio
async def test_customer_subscription_created_handles_null_metadata_gracefully():
    """A customer.subscription.created event with metadata=None must not raise AttributeError."""
    event = {
        'type': 'customer.subscription.created',
        'data': {
            'object': {
                'id': 'sub_test_null_metadata',
                'customer': None,
                'metadata': None,
            }
        },
    }

    # In unpatched code, subscription_obj.get('metadata', {}).get('uid') raises AttributeError
    with patch('routers.payment.record_subscription_event'):
        result = await _handle_stripe_event(event)
        assert result == {'status': 'success', 'message': 'No customer ID or UID in subscription event.'}


@pytest.mark.asyncio
async def test_subscription_schedule_completed_handles_null_metadata_gracefully():
    """A subscription_schedule.completed event with metadata=None must not raise AttributeError."""
    event = {
        'type': 'subscription_schedule.completed',
        'data': {
            'object': {
                'id': 'sched_test_null_metadata',
                'status': 'completed',
                'metadata': None,
            }
        },
    }

    # In unpatched code, schedule_obj.get('metadata', {}).get('uid') raises AttributeError
    # It should complete gracefully without raising AttributeError
    await _handle_stripe_event(event)


@pytest.mark.asyncio
async def test_checkout_session_completed_with_client_reference_id_and_null_metadata():
    """Pin fallback ordering: client_reference_id resolves uid when metadata is null."""
    event = {
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': 'cs_test_client_ref_null_metadata',
                'client_reference_id': 'test_uid_1234',
                'metadata': None,
            }
        },
    }

    with patch('routers.payment.users_db.get_user_profile', return_value=None):
        result = await _handle_stripe_event(event)
        assert result == {'status': 'success'}
