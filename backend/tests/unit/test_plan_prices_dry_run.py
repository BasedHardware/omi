"""Offline executable proposal and refusal boundary."""

import copy
import importlib.util
import json

import pytest
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/plan_prices_dry_run.py'


def test_proposal_uses_catalog_products_and_exact_ladder_prices():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=True)
    output = json.loads(result.stdout)
    calls = [row['kwargs'] for row in output['create_calls']]
    assert [row['unit_amount'] for row in calls] == [1999, 19990, 4999, 49990]
    assert [row['product'] for row in calls] == ['prod_Uu5HDt3sygCK8N'] * 2 + ['prod_ULep5SEo0pSdaM'] * 2
    assert [row['recurring']['interval'] for row in calls] == ['month', 'year', 'month', 'year']
    assert all(row['metadata']['entitlement_version'] == 'ladder_v1' for row in calls)
    assert len(output['catalog_diff']['append_to_ladder_v1_stripe_prices']) == 4


def test_execute_refuses_before_reading_even_a_missing_fixture():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--execute', '--inventory-fixture', '/missing'], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "David's approval is required" in result.stderr
    assert not result.stdout


def test_inventory_fixture_is_reported(tmp_path):
    fixture = tmp_path / 'inventory.json'
    fixture.write_text(json.dumps({'products': [{'id': 'fixture_product'}], 'prices': []}))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--inventory-fixture', str(fixture)], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout)['inventory']['products'] == [{'id': 'fixture_product'}]


FIXTURE = Path(__file__).parent / 'fixtures/storefront/price_proposal.json'


def load_tool():
    spec = importlib.util.spec_from_file_location('price_proposal_tool', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs():
    root = SCRIPT.parents[1]
    return (
        json.loads((root / 'config/storefront_ladder.json').read_text()),
        json.loads((root / 'config/plan_catalog.json').read_text()),
    )


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_checked_fixture_matches_four_creates_and_appendable_w3_diff(environment):
    fixture = json.loads(FIXTURE.read_text())
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--inventory-fixture', str(FIXTURE), '--environment', environment],
        capture_output=True,
        text=True,
        check=True,
    )
    output = json.loads(result.stdout)
    assert output['create_calls'] == fixture['expected_create_calls']
    assert len(output['create_calls']) == 4
    diff = output['catalog_diff']
    rows = diff['append_to_recognized_stripe_prices']
    ids = diff['append_to_ladder_v1_stripe_prices']
    assert ids == [row['price_id'] for row in rows]
    assert set(ids) == set(output['placeholder_ids']) and len(set(ids)) == 4
    for row, call in zip(rows, fixture['expected_create_calls']):
        assert set(row) == {'price_id', 'plan_id', 'interval', 'environment', 'entitlement_version'}
        assert row['price_id'].startswith('price_W5PLACEHOLDER')
        assert row['price_id'].removeprefix('price_').isalnum()
        assert 'REPLACE' in output['placeholder_ids'][row['price_id']]
        assert row['plan_id'] == call['kwargs']['metadata']['plan_id']
        assert row['interval'] == call['kwargs']['recurring']['interval']
        assert row['entitlement_version'] == 'ladder_v1'
        assert row['environment'] == environment


def test_fixture_drift_fails_instead_of_echoing_it(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    fixture['expected_create_calls'][0]['kwargs']['unit_amount'] += 1
    path = tmp_path / 'drift.json'
    path.write_text(json.dumps(fixture))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--inventory-fixture', str(path)], capture_output=True, text=True
    )
    assert result.returncode != 0 and not result.stdout
    assert 'does not match proposed creates' in result.stderr


@pytest.mark.parametrize('plan', ['plus', 'operator', 'unlimited'])
def test_ambiguous_product_plan_is_rejected(plan):
    ladder, catalog = inputs()
    if plan == 'unlimited':
        ladder['tiers'].append({'plan_id': plan, 'proposed_prices': {'month': 1999}})
    else:
        row = next(row for row in catalog['recognized_stripe_products'] if row['plan_id'] == plan)
        catalog['recognized_stripe_products'].append(copy.deepcopy(row))
    with pytest.raises(ValueError, match='duplicate or missing plan_id'):
        load_tool().proposal(ladder, catalog, {})


def test_duplicate_ladder_plan_is_rejected():
    ladder, catalog = inputs()
    ladder['tiers'].append(copy.deepcopy(ladder['tiers'][1]))
    with pytest.raises(ValueError, match='duplicate plan_id'):
        load_tool().proposal(ladder, catalog, {})


def test_invalid_environment_is_rejected():
    ladder, catalog = inputs()
    with pytest.raises(ValueError, match='environment must be dev or prod'):
        load_tool().proposal(ladder, catalog, {}, '<dev_or_prod>')
