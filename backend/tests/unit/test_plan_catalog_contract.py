from __future__ import annotations

import subprocess
from copy import deepcopy

import pytest

from scripts import generate_plan_catalog as plan_catalog_compiler
from config.plan_catalog import (
    MEASUREMENT_CONTRACTS,
    PAID_PLAN_IDS,
    PLAN_TYPE_VALUES,
    RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
    PlanType,
    allocation_limit,
    configured_billing_price_plans,
    get_plan_allocation,
    get_plan_contract,
    plan_uses_overage,
    resolve_stripe_price_plan,
)
from scripts.generate_plan_catalog import (
    GENERATED_PATH,
    catalog_digest,
    load_catalog,
    render_generated,
    scan_embedded_stripe_ids,
    validate_catalog,
    validate_compatibility,
    validate_publishable_catalog,
)


def test_catalog_is_valid_and_generated_projection_is_current():
    catalog = load_catalog()

    assert validate_catalog(catalog) == []
    assert GENERATED_PATH.read_text(encoding='utf-8') == render_generated(catalog)


def test_source_scan_covers_production_code_and_ignores_tests_and_docs(tmp_path, monkeypatch):
    source = tmp_path / 'service' / 'plans.ts'
    source.parent.mkdir()
    source.write_text("const id = 'price_1234567890abcdef';", encoding='utf-8')
    dockerfile = tmp_path / 'worker' / 'Dockerfile'
    dockerfile.parent.mkdir()
    dockerfile.write_text('ENV PRODUCT_ID=prod_1234567890abcd\n', encoding='utf-8')
    ignored_test = tmp_path / 'tests' / 'fixture.py'
    ignored_test.parent.mkdir()
    ignored_test.write_text("PRICE = 'price_ignored1234567890'", encoding='utf-8')
    ignored_doc = tmp_path / 'docs' / 'inventory.md'
    ignored_doc.parent.mkdir()
    ignored_doc.write_text('prod_ignored1234567890', encoding='utf-8')
    monkeypatch.setattr(plan_catalog_compiler, 'ROOT', tmp_path)

    assert scan_embedded_stripe_ids(load_catalog()) == [
        'service/plans.ts: embedded Stripe price price_1234567890abcdef is absent from plan_catalog.json',
        'worker/Dockerfile: embedded Stripe product prod_1234567890abcd is absent from plan_catalog.json',
    ]


def test_source_scan_skips_gitignored_sibling_worktrees(tmp_path, monkeypatch):
    """A gitignored sibling worktree is not part of the tree CI checks out.

    `.claude/worktrees/` is a documented multi-worktree pattern, and each entry holds a
    full copy of the repo. Scanning into them fails `plan-catalog-contract` locally on
    files that are untracked, absent from the diff, and absent in CI, so the gate reads
    as broken and the only way past it is a skip hatch (#12476).
    """
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True, timeout=60)
    (tmp_path / '.gitignore').write_text('.claude/\n', encoding='utf-8')

    tracked = tmp_path / 'service' / 'plans.ts'
    tracked.parent.mkdir()
    tracked.write_text("const id = 'price_1234567890abcdef';", encoding='utf-8')

    stale = tmp_path / '.claude' / 'worktrees' / 'old-session' / 'backend' / 'charts' / 'values.yaml'
    stale.parent.mkdir(parents=True)
    stale.write_text("priceId: price_stale1234567890\nproductId: prod_stale1234567\n", encoding='utf-8')

    monkeypatch.setattr(plan_catalog_compiler, 'ROOT', tmp_path)

    assert scan_embedded_stripe_ids(load_catalog()) == [
        'service/plans.ts: embedded Stripe price price_1234567890abcdef is absent from plan_catalog.json',
    ]


def test_plan_identity_and_paid_membership_are_complete():
    assert PLAN_TYPE_VALUES == {
        'basic',
        'unlimited',
        'architect',
        'operator',
        'plus',
        'unlimited_v2',
    }
    assert PAID_PLAN_IDS == PLAN_TYPE_VALUES - {'basic'}
    assert PlanType('pro') is PlanType.architect


def test_support_scanner_derives_every_paid_plan_and_retained_price():
    from scripts.support.find_stripe_entitlement_mismatches import DEFAULT_PRICE_TO_PLAN, PAID_PLANS

    assert PAID_PLANS == set(PAID_PLAN_IDS)
    assert DEFAULT_PRICE_TO_PLAN == {
        price_id: plan.value for price_id, plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items()
    }


@pytest.mark.parametrize(
    ('price_id', 'expected_plan'),
    [
        # B2: both dev services' Architect prices remain recognized.
        ('price_1TLFXK1F8wnoWYvwG1TaUkZ3', PlanType.architect),
        ('price_1TN7s21F8wnoWYvwG6JuEFm6', PlanType.architect),
        # B6: actively sold production IDs are retained without a "legacy" assumption.
        ('price_1RtJPm1F8wnoWYvwhVJ38kLb', PlanType.unlimited),
        ('price_1RtJQ71F8wnoWYvwKMPaGlGY', PlanType.unlimited),
        ('price_1TAfBB1F8wnoWYvw8XBFM1dX', PlanType.architect),
        ('price_1TLFac1F8wnoWYvwtPxZhtzE', PlanType.architect),
        # Current production consumer-plan prices.
        ('price_1TuH6z1F8wnoWYvw7Siv61SX', PlanType.plus),
        ('price_1TuHCw1F8wnoWYvwZvKu86sI', PlanType.plus),
        ('price_1TuIa81F8wnoWYvw0iX0j5M8', PlanType.unlimited_v2),
        ('price_1TuIap1F8wnoWYvwHWq0EvNU', PlanType.unlimited_v2),
    ],
)
def test_every_known_billed_price_resolves_without_live_stripe(price_id: str, expected_plan: PlanType):
    assert RECOGNIZED_STRIPE_PRICE_PLAN_TYPES[price_id] is expected_plan
    assert resolve_stripe_price_plan(price_id, {}) is expected_plan


def test_entire_recognition_ledger_resolves_without_live_stripe():
    for price_id, expected_plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items():
        assert resolve_stripe_price_plan(price_id, {}) is expected_plan


def test_configured_price_aliases_derive_plan_ownership_from_catalog():
    configured = configured_billing_price_plans(
        {
            'STRIPE_ARCHITECT_MONTHLY_PRICE_ID': 'price_same',
            'STRIPE_PRO_MONTHLY_PRICE_ID': 'price_same',
            'STRIPE_PLUS_MONTHLY_PRICE_ID': 'price_plus',
        }
    )

    assert configured == {'price_same': PlanType.architect, 'price_plus': PlanType.plus}


def test_configured_price_cannot_be_assigned_to_two_plans():
    with pytest.raises(ValueError, match='both architect and plus'):
        configured_billing_price_plans(
            {
                'STRIPE_ARCHITECT_MONTHLY_PRICE_ID': 'price_conflict',
                'STRIPE_PLUS_MONTHLY_PRICE_ID': 'price_conflict',
            }
        )


def test_typed_allocations_resolve_owner_policy_without_zero_unlimited_convention():
    assert allocation_limit(PlanType.basic, 'transcription') == 18_000
    assert get_plan_allocation(PlanType.basic, 'transcription')['limit'] == {
        'kind': 'finite',
        'value': 18_000,
    }

    architect_chat = get_plan_allocation(PlanType.architect, 'chat')
    assert architect_chat['unit'] == 'usd_cent'
    assert allocation_limit(PlanType.architect, 'chat') == 40_000
    assert get_plan_allocation(PlanType.operator, 'chat')['unit'] == 'question'

    assert plan_uses_overage(PlanType.unlimited)
    assert plan_uses_overage(PlanType.operator)
    assert plan_uses_overage(PlanType.architect)
    assert not plan_uses_overage(PlanType.basic)
    assert not plan_uses_overage(PlanType.plus)
    assert not plan_uses_overage(PlanType.unlimited_v2)
    assert get_plan_allocation(PlanType.plus, 'chat')['exhaustion'] == {'kind': 'hard_cap'}
    assert get_plan_allocation(PlanType.unlimited_v2, 'chat')['exhaustion'] == {'kind': 'hard_cap'}


def test_measurement_contract_makes_cost_visibility_explicit():
    assert MEASUREMENT_CONTRACTS['chat']['cost_status'] == 'partial'
    assert MEASUREMENT_CONTRACTS['transcription']['cost_status'] == 'missing'
    assert (
        'backend/database/llm_usage.py:plan_usage.<plan_id>.*.cost_usd' in MEASUREMENT_CONTRACTS['chat']['cost_source']
    )
    assert (
        'backend/database/llm_gateway_accounting.py:estimated_cost_micro_usd'
        in MEASUREMENT_CONTRACTS['chat']['cost_source']
    )
    assert 'BYOK provider cost is explicitly excluded' in MEASUREMENT_CONTRACTS['chat']['limitation']
    assert 'BYOK cost are explicitly excluded' in MEASUREMENT_CONTRACTS['transcription']['limitation']

    errors = validate_publishable_catalog(load_catalog())
    assert 'publishable: basic.transcription still requires B1' not in errors
    assert 'publishable: plus.chat still requires B3' not in errors
    assert 'publishable: unlimited_v2.chat still requires B3' not in errors
    assert 'publishable: chat cost accounting is not complete' in errors


def test_joined_plan_contract_answers_policy_and_cost_coverage_in_one_query():
    contract = get_plan_contract(PlanType.architect)

    assert contract['plan']['id'] == 'architect'
    assert contract['plan']['desktop_profile'] == 'desktop_architect'
    assert contract['features']['chat']['policy']['unit'] == 'usd_cent'
    assert contract['features']['chat']['policy']['limit']['value'] == 40_000
    assert contract['features']['chat']['measurement']['cost_status'] == 'partial'


def test_compatibility_guard_rejects_destructive_identity_and_billing_changes():
    previous = load_catalog()
    current = deepcopy(previous)
    current['catalog_revision'] += 1
    current['plans'] = [plan for plan in current['plans'] if plan['id'] != 'plus']
    current['recognized_stripe_prices'] = [
        entry for entry in current['recognized_stripe_prices'] if entry['price_id'] != 'price_1RtJPm1F8wnoWYvwhVJ38kLb'
    ]
    for entry in current['recognized_stripe_products']:
        if entry['product_id'] == 'prod_U8x5HNGnTF50X1':
            entry['plan_id'] = 'operator'

    errors = validate_compatibility(previous, current)
    assert "plan 'plus' cannot be removed" in '\n'.join(errors)
    assert 'price_1RtJPm1F8wnoWYvwhVJ38kLb cannot be removed' in '\n'.join(errors)
    assert "prod_U8x5HNGnTF50X1 cannot change from 'architect' to 'operator'" in '\n'.join(errors)


def test_compatibility_guard_requires_revision_bump():
    previous = load_catalog()
    current = deepcopy(previous)
    current['plans'][0]['display_name'] = 'Changed'

    assert 'compatibility: catalog_revision must increase when the catalog changes' in validate_compatibility(
        previous, current
    )
