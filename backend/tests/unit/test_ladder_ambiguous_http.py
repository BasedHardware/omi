"""Standalone shadow usage retains recorded units without ladder-only proxy enforcement."""

from datetime import datetime, timezone

import pytest

from tests.unit.fixtures.shadow_usage_firestore import Store


@pytest.mark.parametrize('retired_env', ['true', 'false'])
def test_standalone_shadow_usage_preserves_recorded_units(monkeypatch, retired_env):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', retired_env)
    from database import usage_units
    from utils import ladder_v1 as ladder

    monkeypatch.setattr(
        ladder,
        'account',
        lambda *a, **k: {
            'plan_id': 'plus',
            'entitlement_version': 'ladder_v1',
            'budget': {'kind': 'units', 'value': 100000},
        },
    )
    now = datetime.now(timezone.utc)
    leaf = {'micro_units': 123456, 'legacy_counter_seconds': 600, 'status_counts': {'complete': 5, 'missing': 1}}
    store = Store(
        {
            'users/u/hourly_usage/'
            + now.strftime('%Y-%m-%d-%H'): {
                'year': now.year,
                'month': now.month,
                'transcription_seconds': 600,
                'shadow_v1': {'features': {'transcription': {'funding': {'omi': leaf}}}},
            }
        }
    )
    monkeypatch.setattr(usage_units, 'get_customer_firestore_client', lambda: store)
    snapshot = ladder.usage_snapshot('u', firestore_client=store)
    assert snapshot['used_units'] == 123456 / 1_000_000
    assert 'ambiguous_priced_transcription_seconds' not in snapshot['completeness']
    assert ladder.budget_snapshot('u', firestore_client=store) is None
