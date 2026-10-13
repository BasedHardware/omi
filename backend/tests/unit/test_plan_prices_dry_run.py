"""Offline executable proposal and refusal boundary."""

import json
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
