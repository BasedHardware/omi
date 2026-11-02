"""Golden captured through main's runtime resolver before any W3 changes.

Baseline: b8076bab847fa35f3924ca456b88216cae851e9f. The generation
ran through backend/test.sh; snapshot.py is the capture procedure.
"""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.plan_catalog import (
    architect_ladder_v1_budget_units,
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


def _period(days: int) -> float:
    return (datetime.now(timezone.utc) + timedelta(days=days)).timestamp()


def test_free_and_old_paid_records_stay_legacy():
    assert resolve_subscription_entitlements({})['entitlement_version'] == 'legacy'
    open_paid = resolve_subscription_entitlements({'plan': 'operator', 'current_period_end': _period(1)})
    assert open_paid['plan_id'] == 'operator'
    assert open_paid['budget'] is None
    assert resolve_subscription_entitlements({'plan': 'operator', 'status': 'inactive'})['plan_id'] == 'basic'
    basic = get_entitlement_version('basic')
    assert resolve_subscription_entitlements({'plan': 'operator'}) == basic
    assert resolve_subscription_entitlements({'plan': 'operator', 'status': 'active', 'current_period_end': 0}) == basic
    assert (
        resolve_subscription_entitlements({'plan': 'operator', 'status': 'trialing', 'current_period_end': _period(-1)})
        == basic
    )
    assert (
        resolve_subscription_entitlements(
            {
                'plan': 'plus',
                'status': 'active',
                'current_price_id': 'price_1TuH6z1F8wnoWYvw7Siv61SX',
                'current_period_end': _period(-1),
            },
            {},
        )
        == basic
    )


def test_ladder_budgets_exist_without_activating_any_price():
    assert LADDER_V1_STRIPE_PRICES == []
    assert get_entitlement_version('plus', 'ladder_v1')['budget']['value'] == 16360
    assert get_entitlement_version('operator', 'ladder_v1')['budget']['value'] == 44090
    assert get_entitlement_version('architect', 'ladder_v1')['budget']['value'] == 189463
    assert architect_ladder_v1_budget_units() == 189463
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
    result = resolve_subscription_entitlements(
        {'plan': 'unlimited', 'current_price_id': 'price_fixture', 'current_period_end': _period(1)}, {}
    )
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


@pytest.mark.parametrize('status', ['active', 'trialing'])
def test_paid_status_resolves_price_before_stored_label(status):
    result = resolve_subscription_entitlements(
        {
            'plan': 'unlimited',
            'status': status,
            'current_price_id': 'price_1TuH6z1F8wnoWYvw7Siv61SX',
            'current_period_end': _period(1),
        },
        {},
    )
    assert result == get_entitlement_version('plus')


@pytest.mark.parametrize('status', ['inactive', 'past_due', 'canceled', 'unpaid', 'incomplete'])
def test_nonpaying_status_demotes_recognized_price(status):
    assert resolve_subscription_entitlements(
        {'plan': 'plus', 'status': status, 'current_price_id': 'price_1TuH6z1F8wnoWYvw7Siv61SX'}, {}
    ) == get_entitlement_version('basic')


@pytest.mark.parametrize('status', ['active', 'trialing'])
def test_unknown_price_preserves_stored_legacy_plan_and_logs(status, caplog):
    result = resolve_subscription_entitlements(
        {'plan': 'operator', 'status': status, 'current_price_id': 'price_unknown', 'current_period_end': _period(1)},
        {},
    )
    assert result == get_entitlement_version('operator')
    assert 'retaining stored plan legacy entitlements' in caplog.text


def test_known_price_env_conflict_does_not_fall_back():
    with pytest.raises(ValueError, match='retained'):
        resolve_subscription_entitlements(
            {
                'plan': 'plus',
                'status': 'active',
                'current_price_id': 'price_1TuH6z1F8wnoWYvw7Siv61SX',
                'current_period_end': _period(1),
            },
            {'STRIPE_UNLIMITED_MONTHLY_PRICE_ID': 'price_1TuH6z1F8wnoWYvw7Siv61SX'},
        )


def test_missing_ladder_price_id_returns_validation_error():
    from scripts.entitlement_catalog_validation import validate_entitlement_versions

    catalog = deepcopy(load_catalog())
    catalog['recognized_stripe_prices'].append({'entitlement_version': 'ladder_v1', 'plan_id': 'plus'})
    assert any('requires a nonempty price_id' in error for error in validate_entitlement_versions(catalog))


def test_generated_exports_include_entitlement_constants():
    from config import plan_catalog_generated

    assert {'ENTITLEMENT_VERSIONS', 'LADDER_V1_STRIPE_PRICES', 'RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS'} <= set(
        plan_catalog_generated.__all__
    )


@pytest.mark.parametrize('price', ['price_1TuH6z1F8wnoWYvw7Siv61SX', None])
def test_inactive_paid_subscription_keeps_entitlements_until_period_end(price):
    result = resolve_subscription_entitlements(
        {
            'plan': 'plus',
            'status': 'inactive',
            'current_price_id': price,
            'current_period_end': (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
        },
        {},
    )
    assert result == get_entitlement_version('plus')


@pytest.mark.parametrize('status', ['inactive', 'past_due', 'canceled', 'unpaid', 'incomplete'])
def test_expired_inactive_or_stripe_nonpaying_status_demotes(status):
    end = datetime.now(timezone.utc) + timedelta(days=-1 if status == 'inactive' else 1)
    assert resolve_subscription_entitlements(
        {
            'plan': 'plus',
            'status': status,
            'current_price_id': 'price_1TuH6z1F8wnoWYvw7Siv61SX',
            'current_period_end': end.timestamp(),
        },
        {},
    ) == get_entitlement_version('basic')


def test_raw_legacy_free_resolves_basic():
    assert resolve_subscription_entitlements({'plan': 'free'}) == get_entitlement_version('basic')


def test_compatibility_returns_error_for_missing_plan_keys():
    baseline = load_catalog()
    missing_id = deepcopy(baseline)
    del missing_id['plans'][0]['id']
    id_errors = validate_compatibility(baseline, missing_id)
    assert any('plan requires an id' in error for error in id_errors)
    missing_key = deepcopy(baseline)
    del missing_key['plans'][0]['allocations']
    key_errors = validate_compatibility(baseline, missing_key)
    assert any('missing legacy entitlement key allocations' in error for error in key_errors)


def test_cli_check_with_base_ref_reports_missing_plan_key(monkeypatch, capsys):
    from argparse import Namespace
    from scripts import generate_plan_catalog as generator

    baseline = load_catalog()
    malformed = deepcopy(baseline)
    del malformed['plans'][0]['allocations']
    monkeypatch.setattr(
        generator,
        'parse_args',
        lambda: Namespace(check=True, base_ref='origin/main', skip_source_scan=False, require_publishable=False),
    )
    monkeypatch.setattr(generator, 'load_catalog', lambda: malformed)
    monkeypatch.setattr(generator, 'load_catalog_from_git', lambda ref: baseline)
    monkeypatch.setattr(generator, 'scan_embedded_stripe_ids', lambda catalog: [])
    assert generator.main() == 1
    assert 'missing legacy entitlement key allocations' in capsys.readouterr().err


def test_compatibility_returns_error_for_missing_price_id():
    baseline = load_catalog()
    malformed = deepcopy(baseline)
    malformed['recognized_stripe_prices'].append({'entitlement_version': 'ladder_v1', 'plan_id': 'plus'})
    assert any('nonempty price_id' in e for e in validate_compatibility(baseline, malformed))


def test_cli_check_with_base_ref_reports_missing_price_id(monkeypatch, capsys):
    from argparse import Namespace
    from scripts import generate_plan_catalog as generator

    baseline = load_catalog()
    malformed = deepcopy(baseline)
    malformed['recognized_stripe_prices'].append({'entitlement_version': 'ladder_v1', 'plan_id': 'plus'})
    monkeypatch.setattr(
        generator,
        'parse_args',
        lambda: Namespace(check=True, base_ref='origin/main', skip_source_scan=False, require_publishable=False),
    )
    monkeypatch.setattr(generator, 'load_catalog', lambda: malformed)
    monkeypatch.setattr(generator, 'load_catalog_from_git', lambda ref: baseline)
    monkeypatch.setattr(generator, 'scan_embedded_stripe_ids', lambda catalog: [])
    assert generator.main() == 1
    assert 'nonempty price_id' in capsys.readouterr().err


@pytest.mark.parametrize('price,plan', sorted(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items()))
def test_every_recognized_paid_legacy_price_retains_cloud_screen_vectors(price, plan):
    resolved = resolve_price_entitlements(price, {})
    assert resolved['entitlement_version'] == 'legacy'
    assert resolved['capabilities']['cloud_screen_vectors'] is True
    assert resolved['plan_id'] == plan.value


@pytest.mark.parametrize('plan,allowed', [('basic', False), ('plus', False), ('operator', True), ('architect', True)])
def test_ladder_cloud_screen_capability_is_price_versioned(plan, allowed):
    assert get_entitlement_version(plan, 'ladder_v1')['capabilities']['cloud_screen_vectors'] is allowed
    if plan != 'basic':
        assert get_entitlement_version(plan, 'legacy')['capabilities']['cloud_screen_vectors'] is True
