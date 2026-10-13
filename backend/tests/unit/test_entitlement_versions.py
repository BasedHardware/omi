"""Golden captured through main's runtime resolver before any W3 changes.

Baseline: b8076bab847fa35f3924ca456b88216cae851e9f. The generation
ran through backend/test.sh; snapshot.py is the capture procedure.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from config.plan_catalog import (
    get_entitlement_version,
    resolve_price_entitlements,
    resolve_subscription_entitlements,
)
from config.plan_catalog import RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from config.plan_catalog_generated import LADDER_V1_STRIPE_PRICES
from scripts.generate_plan_catalog import load_catalog, validate_catalog, validate_compatibility
from tests.unit.fixtures.entitlements.snapshot import legacy_snapshot

GOLDEN = Path(__file__).parent / 'fixtures/entitlements/main_b8076bab847.json'


@pytest.fixture(scope="module")
def captured_legacy():
    # Import the heavy subscription graph in setup, as test_subscription_restructure does.
    return legacy_snapshot()


def test_all_main_legacy_price_entitlements_are_byte_identical(captured_legacy):
    captured = captured_legacy
    assert json.dumps(captured, sort_keys=True, separators=(',', ':')) + '\n' == GOLDEN.read_text()
    expected = json.loads(GOLDEN.read_text())
    assert set(expected) == set(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES)
    for price, snapshot in expected.items():
        resolved = resolve_price_entitlements(price, {})
        assert resolved['entitlement_version'] == 'legacy'
        assert resolved['budget'] is None
        assert resolved['policy'] == snapshot['definition']


def test_free_and_old_paid_records_stay_legacy():
    assert resolve_subscription_entitlements({})['entitlement_version'] == 'legacy'
    assert resolve_subscription_entitlements({'plan': 'operator'})['budget'] is None
    assert resolve_subscription_entitlements({'plan': 'operator', 'status': 'inactive'})['plan_id'] == 'basic'


def test_ladder_budgets_exist_without_activating_any_price():
    assert LADDER_V1_STRIPE_PRICES == []
    assert get_entitlement_version('plus', 'ladder_v1')['budget']['value'] == 16360
    assert get_entitlement_version('operator', 'ladder_v1')['budget']['value'] == 44090
    assert get_entitlement_version('architect', 'ladder_v1')['budget']['value'] == 189463
    assert get_entitlement_version('basic', 'ladder_v1')['budget']['speech_seconds'] == 18000
    with pytest.raises(ValueError):
        get_entitlement_version('unlimited', 'ladder_v1')
    with pytest.raises(ValueError):
        resolve_price_entitlements('price_unknown', {})


def test_fixture_ladder_price_resolves_by_price_without_env_activation(monkeypatch):
    import config.plan_catalog as versions
    import config.plan_catalog as catalog

    monkeypatch.setitem(catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES, 'price_fixture', catalog.PlanType.plus)
    monkeypatch.setitem(versions.RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS, 'price_fixture', 'ladder_v1')
    result = resolve_subscription_entitlements({'plan': 'unlimited', 'current_price_id': 'price_fixture'}, {})
    assert result['plan_id'] == 'plus'
    assert result['entitlement_version'] == 'ladder_v1'
    assert result['budget']['value'] == 16360
    # Environment-only prices cannot activate a new entitlement version.
    assert (
        resolve_price_entitlements('price_env', {'STRIPE_PLUS_MONTHLY_PRICE_ID': 'price_env'})['entitlement_version']
        == 'legacy'
    )


def test_validator_rejects_drift_and_activation_without_recognition():
    baseline = load_catalog()
    current = deepcopy(baseline)
    current['ladder_v1_stripe_prices'] = ['price_fixture']
    assert any('must match' in e for e in validate_catalog(current))
    current = deepcopy(baseline)
    current['recognized_stripe_prices'][0]['entitlement_version'] = 'ladder_v1'
    assert any('cannot change entitlement version' in e for e in validate_compatibility(baseline, current))
    current = deepcopy(baseline)
    current['plans'][0]['allocations']['transcription']['limit']['value'] -= 1
    assert any('legacy entitlements cannot change' in e for e in validate_compatibility(baseline, current))
