"""Unit tests for explicit null and timestamp guards in usage_units and billing_reconciliation."""

from datetime import datetime, timezone

from database import usage_units
from utils.billing_reconciliation import _price_id, reconcile


def test_historical_quantity_and_summarize_usage_handle_explicit_null_submaps():
    """_historical_quantity() and summarize_usage() should not raise AttributeError or TypeError on explicit None maps."""
    leaf_with_nulls = {
        'events': 5,
        'quantity_attributed_events': None,
        'micro_units': 1000,
        'quantity_attributed_micro_units': None,
        'status_counts': None,
    }
    assert usage_units._historical_quantity(leaf_with_nulls, 'events') == (5.0, 1000, 0)

    version = next(iter(usage_units.RATE_CARD_SHA256))
    hourly = [
        {
            f'shadow_{version}': {
                'features': {
                    'transcription': {
                        'funding': {
                            'omi': {
                                'micro_units': 500,
                                'legacy_counter_seconds': 10,
                                'status_counts': None,
                            }
                        }
                    },
                    'malformed_feature': {'funding': None},
                },
                'lanes': None,
            },
            'transcription_seconds': None,
        }
    ]
    days = [
        (
            {
                f'shadow_{version}': {
                    'hours': {
                        '00': {
                            'features': {
                                'chat': {
                                    'funding': {
                                        'omi': {
                                            'micro_units': 250,
                                            'events': 1,
                                            'status_counts': None,
                                        }
                                    }
                                },
                                'empty_funding': {'funding': None},
                            }
                        },
                        '01': {'features': None},
                    }
                },
                'attempts': None,
            },
            {'micro_units': 0},
        )
    ]

    summary = usage_units.summarize_usage(
        hourly,
        days,
        entitlements={'entitlement_version': 'legacy'},
        enforcing=True,
        read_versions=(version,),
    )
    assert summary['totals']['transcription'] >= 500
    assert summary['totals']['chat'] >= 250


def test_billing_reconciliation_price_id_guards_explicit_null_items_and_price():
    """_price_id() should return None instead of raising AttributeError when items, data, or price is explicitly None."""
    assert _price_id({'items': None}) is None
    assert _price_id({'items': {'data': None}}) is None
    assert _price_id({'items': {'data': [None]}}) is None
    assert _price_id({'items': {'data': [{'price': None}]}}) is None
    assert _price_id({'items': {'data': [{'price': {'id': 'price_123'}}]}}) == 'price_123'


def test_billing_reconciliation_handles_explicit_null_plan_and_datetime_period_end():
    """reconcile() should treat explicit plan=None as basic and coerce datetime/string period_end timestamps."""
    as_of = int(datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc).timestamp())
    future_dt = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)

    # User with explicit plan=None should NOT be classified as paid_in_firestore_no_stripe_entitlement
    users = [
        {
            'uid': 'u-null-plan',
            'subscription': {
                'plan': None,
                'current_period_end': future_dt,
            },
        }
    ]
    report = reconcile([], users, {'price_unlimited': 'unlimited'}, as_of=as_of)
    assert report.counts['paid_in_firestore_no_stripe_entitlement'] == 0

    # User with paid plan and datetime current_period_end matching Stripe epoch int should reconcile cleanly
    paid_users = [
        {
            'uid': 'u-paid',
            'subscription': {
                'plan': 'unlimited',
                'stripe_subscription_id': 'sub_1',
                'current_price_id': 'price_unlimited',
                'current_period_end': future_dt,
            },
        }
    ]
    subs = [
        {
            'id': 'sub_1',
            'status': 'active',
            'metadata': {'uid': 'u-paid'},
            'items': {'data': [{'price': {'id': 'price_unlimited'}}]},
            'current_period_end': int(future_dt.timestamp()),
        }
    ]
    paid_report = reconcile(subs, paid_users, {'price_unlimited': 'unlimited'}, as_of=as_of)
    assert paid_report.counts['stale_period'] == 0
    assert paid_report.counts['wrong_plan'] == 0
