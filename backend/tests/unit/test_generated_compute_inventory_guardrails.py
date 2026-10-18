"""Require declared funded admission for new inventoried model entrypoints."""

import ast
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]
GATE_CALLS = {
    'require_generated_compute',
    'generated_compute_allowed',
    'require_current_generated_compute',
    'current_generated_compute_allowed',
    '_require_client_budget',
}


def _function(path, name):
    tree = ast.parse((BACKEND / path).read_text())
    return next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _calls(node):
    # run_blocking passes the gate function as an argument, so audit Name nodes too.
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def test_every_inventory_surface_declares_a_real_funded_gate_or_explicit_non_generated_owner():
    inventory = yaml.safe_load((BACKEND / 'docs/llm/model_endpoint_inventory.yaml').read_text())
    exceptions = {
        'desktop_realtime_usage': 'no_compute_usage_debit',
        'production_like_memory_ingestion': 'system_experiment_requires_explicit_uid_under_enforcement',
    }
    for row in inventory['surfaces']:
        gate = row.get('funded_budget_gate')
        assert gate, f"{row['surface']}: new model entrypoint needs an explicit funded gate"
        if row['surface'] in exceptions:
            assert gate == exceptions[row['surface']]
            continue
        path, name = gate.split(':')
        assert _calls(_function(path, name)) & GATE_CALLS, f"{row['surface']}: declared path is ungated"


def test_get_llm_guard_is_unconditional_for_all_new_feature_names_and_precedes_dispatch():
    function = _function('utils/llm/clients.py', 'get_llm')
    direct_guards = [
        n
        for n in function.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == '_require_client_budget'
    ]
    assert len(direct_guards) == 1, 'Budget guard must not depend on a feature allowlist or optional caller opt-in'
    guard = direct_guards[0].value
    assert isinstance(guard.args[0], ast.Name) and guard.args[0].id == 'feature'
    assert any(k.arg == 'uid' for k in guard.keywords)
    dispatches = [
        n
        for n in ast.walk(function)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id
        in {
            'get_default_client',
            'get_or_create_omi_gateway_llm',
            'get_or_create_omi_gateway_llm_for_byok',
            '_create_byok_client',
        }
    ]
    assert dispatches and all(n.lineno > guard.lineno for n in dispatches)


def test_budget_only_adapter_cannot_activate_free_plan_entitlement_policy_or_monthly_scans():
    tree = ast.parse((BACKEND / 'utils/generated_compute.py').read_text())
    assert not (_calls(tree) & {'authorize_managed_compute', 'budget_snapshot', 'usage_snapshot', 'get_usage_units'})
    assert 'processing_allowed' in {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def test_endpoint_or_inventory_changes_select_the_guard_without_replacing_full_fallback():
    from scripts.select_backend_unit_tests import tests_for_changed_paths

    guard = 'tests/unit/test_generated_compute_inventory_guardrails.py'
    tests = [guard, 'tests/unit/test_chat_quota.py']
    for source in ('backend/docs/llm/model_endpoint_inventory.yaml', 'backend/routers/future_model_endpoint.py'):
        selected, _ = tests_for_changed_paths([source], tests)
        assert guard in selected
    selected, _ = tests_for_changed_paths(['backend/routers/never_mapped_new_feature.py'], tests)
    assert set(selected) == set(tests)
