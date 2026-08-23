#!/usr/bin/env python3
"""Validate the canonical plan catalog and generate its backend projection.

The JSON catalog owns plan facts. This script is the compiler boundary: runtime
code imports the generated Python projection, never reparses JSON at import
time. ``--check`` is hermetic and is the local/CI drift guard.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import pprint
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / 'backend' / 'config' / 'plan_catalog.json'
GENERATED_PATH = ROOT / 'backend' / 'config' / 'plan_catalog_generated.py'
CATALOG_REPO_PATH = CATALOG_PATH.relative_to(ROOT).as_posix()

PLAN_ID_RE = re.compile(r'^[a-z][a-z0-9_]*$')
ENV_VAR_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')
STRIPE_PRICE_ID_RE = re.compile(r'^price_[A-Za-z0-9]+$')
STRIPE_PRODUCT_ID_RE = re.compile(r'^prod_[A-Za-z0-9]+$')
EMBEDDED_PRICE_ID_RE = re.compile(r'(?<![A-Za-z0-9_])(price_[A-Za-z0-9]{16,})(?![A-Za-z0-9_])')
EMBEDDED_PRODUCT_ID_RE = re.compile(r'(?<![A-Za-z0-9_])(prod_[A-Za-z0-9]{12,})(?![A-Za-z0-9_])')

PLAN_KEYS = {
    'id',
    'display_name',
    'wire_aliases',
    'wire_fallback_plan',
    'lifecycle',
    'is_paid',
    'storefronts',
    'desktop_profile',
    'conditional_desktop_profiles',
    'fair_use_profile',
    'phone_calls_profile',
    'allocations',
    'billing',
}
ALLOCATION_KEYS = {'transcription', 'words_transcribed', 'insights_gained', 'memories_created', 'chat'}
STOREFRONTS = {'android', 'ios', 'macos', 'web', 'windows'}
LIFECYCLES = {'current', 'deprecated'}
LIMIT_KINDS = {'finite', 'unlimited', 'decision_required'}
EXHAUSTION_KINDS = {'hard_cap', 'overage', 'decision_required'}
INTERVALS = {'month', 'year'}
SOURCE_EXTENSIONS = {
    '.arb',
    '.cjs',
    '.dart',
    '.env',
    '.ini',
    '.js',
    '.json',
    '.jsx',
    '.mjs',
    '.plist',
    '.properties',
    '.py',
    '.sh',
    '.swift',
    '.tf',
    '.toml',
    '.tpl',
    '.ts',
    '.tsx',
    '.xml',
    '.yaml',
    '.yml',
}
SOURCE_SCAN_EXCLUDED_PARTS = {
    '.dart_tool',
    '.git',
    '.openapi-venv',
    '.venv',
    'Pods',
    '__pycache__',
    '__tests__',
    'build',
    'docs',
    'node_modules',
    'test',
    'tests',
    'testing',
}


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    with path.open(encoding='utf-8') as catalog_file:
        value = json.load(catalog_file)
    if not isinstance(value, dict):
        raise ValueError('catalog root must be an object')
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True)


def catalog_digest(catalog: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(catalog).encode('utf-8')).hexdigest()


def _unexpected_keys(value: Mapping[str, Any], expected: set[str], path: str, errors: list[str]) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        errors.append(f'{path}: missing keys: {", ".join(missing)}')
    if extra:
        errors.append(f'{path}: unknown keys: {", ".join(extra)}')


def _validate_limit(limit: Any, path: str, decisions: set[str], errors: list[str]) -> None:
    if not isinstance(limit, dict):
        errors.append(f'{path}: limit must be an object')
        return
    kind = limit.get('kind')
    if kind not in LIMIT_KINDS:
        errors.append(f'{path}.kind: expected one of {sorted(LIMIT_KINDS)}, got {kind!r}')
        return
    if kind == 'finite':
        _unexpected_keys(limit, {'kind', 'value'}, path, errors)
        value = limit.get('value')
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f'{path}.value: finite limits require a non-negative integer')
    elif kind == 'unlimited':
        _unexpected_keys(limit, {'kind'}, path, errors)
    else:
        _unexpected_keys(limit, {'kind', 'decision_id', 'legacy_runtime_value'}, path, errors)
        decision_id = limit.get('decision_id')
        if decision_id not in decisions:
            errors.append(f'{path}.decision_id: unknown decision {decision_id!r}')
        legacy_value = limit.get('legacy_runtime_value')
        if not isinstance(legacy_value, int) or isinstance(legacy_value, bool) or legacy_value < 0:
            errors.append(f'{path}.legacy_runtime_value: expected a non-negative integer')


def _validate_exhaustion(exhaustion: Any, path: str, decisions: set[str], errors: list[str]) -> None:
    if not isinstance(exhaustion, dict):
        errors.append(f'{path}: exhaustion must be an object')
        return
    kind = exhaustion.get('kind')
    if kind not in EXHAUSTION_KINDS:
        errors.append(f'{path}.kind: expected one of {sorted(EXHAUSTION_KINDS)}, got {kind!r}')
        return
    if kind == 'decision_required':
        _unexpected_keys(exhaustion, {'kind', 'decision_id', 'runtime_until_decided'}, path, errors)
        decision_id = exhaustion.get('decision_id')
        if decision_id not in decisions:
            errors.append(f'{path}.decision_id: unknown decision {decision_id!r}')
        if exhaustion.get('runtime_until_decided') not in {'hard_cap', 'overage'}:
            errors.append(f'{path}.runtime_until_decided: expected hard_cap or overage')
    else:
        _unexpected_keys(exhaustion, {'kind'}, path, errors)


def _validate_allocations(allocations: Any, path: str, decisions: set[str], errors: list[str]) -> None:
    if not isinstance(allocations, dict):
        errors.append(f'{path}: allocations must be an object')
        return
    _unexpected_keys(allocations, ALLOCATION_KEYS, path, errors)
    for allocation_name in sorted(ALLOCATION_KEYS):
        allocation = allocations.get(allocation_name)
        allocation_path = f'{path}.{allocation_name}'
        if not isinstance(allocation, dict):
            errors.append(f'{allocation_path}: allocation must be an object')
            continue
        expected = (
            {'period', 'unit', 'limit', 'exhaustion'} if allocation_name == 'chat' else {'period', 'unit', 'limit'}
        )
        _unexpected_keys(allocation, expected, allocation_path, errors)
        if allocation.get('period') != 'month':
            errors.append(f'{allocation_path}.period: only month is supported in catalog v1')
        unit = allocation.get('unit')
        allowed_units = {
            'transcription': {'second'},
            'words_transcribed': {'word'},
            'insights_gained': {'insight'},
            'memories_created': {'memory'},
            'chat': {'question', 'usd_cent'},
        }[allocation_name]
        if unit not in allowed_units:
            errors.append(f'{allocation_path}.unit: expected one of {sorted(allowed_units)}, got {unit!r}')
        _validate_limit(allocation.get('limit'), f'{allocation_path}.limit', decisions, errors)
        if allocation_name == 'chat':
            _validate_exhaustion(allocation.get('exhaustion'), f'{allocation_path}.exhaustion', decisions, errors)


def _validate_allocation_profiles(profiles: Any, errors: list[str]) -> tuple[set[str], set[str], set[str]]:
    desktop_profiles: set[str] = set()
    fair_use_profiles: set[str] = set()
    phone_call_profiles: set[str] = set()
    if not isinstance(profiles, dict):
        errors.append('catalog.allocation_profiles: expected an object')
        return desktop_profiles, fair_use_profiles, phone_call_profiles

    _unexpected_keys(profiles, {'desktop', 'fair_use', 'phone_calls'}, 'catalog.allocation_profiles', errors)
    for profile_group, destination in (
        ('desktop', desktop_profiles),
        ('fair_use', fair_use_profiles),
        ('phone_calls', phone_call_profiles),
    ):
        group = profiles.get(profile_group)
        if not isinstance(group, dict) or not group:
            errors.append(f'catalog.allocation_profiles.{profile_group}: expected a non-empty object')
        else:
            destination.update(group)

    desktop = profiles.get('desktop')
    if isinstance(desktop, dict):
        for name, profile in desktop.items():
            path = f'catalog.allocation_profiles.desktop.{name}'
            if not isinstance(profile, dict):
                errors.append(f'{path}: expected an object')
                continue
            _unexpected_keys(profile, {'full_desktop', 'cloud_screen_vectors', 'proactivity_daily'}, path, errors)
            if not isinstance(profile.get('full_desktop'), bool):
                errors.append(f'{path}.full_desktop: expected a boolean')
            if not isinstance(profile.get('cloud_screen_vectors'), bool):
                errors.append(f'{path}.cloud_screen_vectors: expected a boolean')
            limits = profile.get('proactivity_daily')
            if not isinstance(limits, dict):
                errors.append(f'{path}.proactivity_daily: expected an object')
                continue
            _unexpected_keys(
                limits, {'proactive_extraction', 'proactive_reasoning'}, f'{path}.proactivity_daily', errors
            )
            for operation, value in limits.items():
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    errors.append(f'{path}.proactivity_daily.{operation}: expected a positive integer')

    fair_use = profiles.get('fair_use')
    if isinstance(fair_use, dict):
        for name, profile in fair_use.items():
            path = f'catalog.allocation_profiles.fair_use.{name}'
            if not isinstance(profile, dict):
                errors.append(f'{path}: expected an object')
                continue
            _unexpected_keys(profile, {'speech_milliseconds'}, path, errors)
            limits = profile.get('speech_milliseconds')
            if not isinstance(limits, dict):
                errors.append(f'{path}.speech_milliseconds: expected an object')
                continue
            windows = {'rolling_day', 'rolling_three_days', 'rolling_week'}
            _unexpected_keys(limits, windows, f'{path}.speech_milliseconds', errors)
            for window, value in limits.items():
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    errors.append(f'{path}.speech_milliseconds.{window}: expected a positive integer')

    phone_calls = profiles.get('phone_calls')
    if isinstance(phone_calls, dict):
        for name, profile in phone_calls.items():
            path = f'catalog.allocation_profiles.phone_calls.{name}'
            if not isinstance(profile, dict):
                errors.append(f'{path}: expected an object')
                continue
            _unexpected_keys(
                profile, {'monthly_calls', 'max_duration_seconds', 'legacy_runtime_override'}, path, errors
            )
            _validate_limit(profile.get('monthly_calls'), f'{path}.monthly_calls', set(), errors)
            _validate_limit(profile.get('max_duration_seconds'), f'{path}.max_duration_seconds', set(), errors)
            override = profile.get('legacy_runtime_override')
            if not isinstance(override, str) or not override:
                errors.append(f'{path}.legacy_runtime_override: expected a non-empty source path')

    return desktop_profiles, fair_use_profiles, phone_call_profiles


def _validate_billing(billing: Any, path: str, is_paid: bool, errors: list[str]) -> None:
    if not is_paid:
        if billing is not None:
            errors.append(f'{path}: a free plan cannot have billing prices')
        return
    if not isinstance(billing, dict):
        errors.append(f'{path}: paid plans require a billing object')
        return
    _unexpected_keys(billing, {'prices'}, path, errors)
    prices = billing.get('prices')
    if not isinstance(prices, list):
        errors.append(f'{path}.prices: expected a list')
        return
    seen_intervals: set[str] = set()
    seen_env_vars: set[str] = set()
    for index, price in enumerate(prices):
        price_path = f'{path}.prices[{index}]'
        if not isinstance(price, dict):
            errors.append(f'{price_path}: expected an object')
            continue
        required = {'interval', 'currency', 'primary_env_var', 'accepted_env_vars'}
        allowed = required
        missing = sorted(required - set(price))
        extra = sorted(set(price) - allowed)
        if missing:
            errors.append(f'{price_path}: missing keys: {", ".join(missing)}')
        if extra:
            errors.append(f'{price_path}: unknown keys: {", ".join(extra)}')
        interval = price.get('interval')
        if interval not in INTERVALS:
            errors.append(f'{price_path}.interval: expected month or year')
        elif interval in seen_intervals:
            errors.append(f'{price_path}.interval: duplicate {interval!r} price')
        else:
            seen_intervals.add(interval)
        currency = price.get('currency')
        if not isinstance(currency, str) or not re.fullmatch(r'[a-z]{3}', currency):
            errors.append(f'{price_path}.currency: expected a lowercase ISO currency code')
        primary_env_var = price.get('primary_env_var')
        accepted_env_vars = price.get('accepted_env_vars')
        if not isinstance(primary_env_var, str) or not ENV_VAR_RE.fullmatch(primary_env_var):
            errors.append(f'{price_path}.primary_env_var: invalid environment variable')
        if not isinstance(accepted_env_vars, list) or not accepted_env_vars:
            errors.append(f'{price_path}.accepted_env_vars: expected a non-empty list')
            continue
        if primary_env_var not in accepted_env_vars:
            errors.append(f'{price_path}.accepted_env_vars: must contain primary_env_var')
        for env_var in accepted_env_vars:
            if not isinstance(env_var, str) or not ENV_VAR_RE.fullmatch(env_var):
                errors.append(f'{price_path}.accepted_env_vars: invalid environment variable {env_var!r}')
            elif env_var in seen_env_vars:
                errors.append(f'{price_path}.accepted_env_vars: duplicate environment variable {env_var}')
            else:
                seen_env_vars.add(env_var)
    if seen_intervals != INTERVALS:
        errors.append(f'{path}.prices: paid plans require exactly month and year prices')


def _find_floats(value: Any, path: str = 'catalog') -> Iterable[str]:
    if isinstance(value, float):
        yield path
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _find_floats(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _find_floats(child, f'{path}[{index}]')


def validate_catalog(catalog: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_root_keys = {
        'schema_version',
        'catalog_revision',
        'authority',
        'open_decisions',
        'allocation_profiles',
        'measurement_contracts',
        'plans',
        'recognized_stripe_prices',
        'recognized_stripe_products',
    }
    _unexpected_keys(catalog, expected_root_keys, 'catalog', errors)
    if catalog.get('schema_version') != 1:
        errors.append('catalog.schema_version: expected 1')
    revision = catalog.get('catalog_revision')
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append('catalog.catalog_revision: expected a positive integer')
    authority = catalog.get('authority')
    # The catalog owns plan identity and the price-ID -> plan mapping. It deliberately
    # owns NO dollar amounts: those are read live from Stripe at request time
    # (routers/payment.py), so there is no second copy of a price to drift. Stripe is
    # the amount authority; the repository is the identity authority.
    expected_authority = {
        'plan_identity': 'catalog',
        'price_identity': 'repository_ledger',
        'price_amount': 'stripe_live',
        'stripe_role': 'price_amount_authority',
        'unknown_caller_policy': 'legacy_contract',
    }
    if authority != expected_authority:
        errors.append(f'catalog.authority: expected {expected_authority!r}')
    decisions_value = catalog.get('open_decisions')
    if not isinstance(decisions_value, dict):
        errors.append('catalog.open_decisions: expected an object')
        decisions: set[str] = set()
    else:
        decisions = set(decisions_value)
        for decision_id, decision in decisions_value.items():
            if not re.fullmatch(r'B[0-9]+', decision_id):
                errors.append(f'catalog.open_decisions.{decision_id}: decision IDs must look like B1')
            if not isinstance(decision, dict) or not isinstance(decision.get('question'), str):
                errors.append(f'catalog.open_decisions.{decision_id}: expected an object with a question')

    profiles = catalog.get('allocation_profiles')
    desktop_profiles, fair_use_profiles, phone_call_profiles = _validate_allocation_profiles(profiles, errors)

    measurement_contracts = catalog.get('measurement_contracts')
    if not isinstance(measurement_contracts, dict):
        errors.append('catalog.measurement_contracts: expected an object')
    else:
        _unexpected_keys(measurement_contracts, ALLOCATION_KEYS, 'catalog.measurement_contracts', errors)
        for allocation_name in sorted(ALLOCATION_KEYS):
            contract = measurement_contracts.get(allocation_name)
            path = f'catalog.measurement_contracts.{allocation_name}'
            if not isinstance(contract, dict):
                errors.append(f'{path}: expected an object')
                continue
            expected = {'usage_status', 'usage_source', 'cost_status', 'cost_source', 'limitation'}
            _unexpected_keys(contract, expected, path, errors)
            if contract.get('usage_status') not in {'complete', 'partial', 'missing'}:
                errors.append(f'{path}.usage_status: expected complete, partial, or missing')
            if contract.get('cost_status') not in {'complete', 'partial', 'missing'}:
                errors.append(f'{path}.cost_status: expected complete, partial, or missing')
            for source_name, status_name in (('usage_source', 'usage_status'), ('cost_source', 'cost_status')):
                source = contract.get(source_name)
                status = contract.get(status_name)
                if status == 'missing' and source is not None:
                    errors.append(f'{path}.{source_name}: missing measurements cannot name a source')
                elif status != 'missing' and (not isinstance(source, str) or not source):
                    errors.append(f'{path}.{source_name}: measured values require a non-empty source')
            if not isinstance(contract.get('limitation'), str):
                errors.append(f'{path}.limitation: expected a string (empty when complete)')

    plans_value = catalog.get('plans')
    if not isinstance(plans_value, list) or not plans_value:
        errors.append('catalog.plans: expected a non-empty list')
        plans: list[dict[str, Any]] = []
    else:
        plans = [plan for plan in plans_value if isinstance(plan, dict)]
        if len(plans) != len(plans_value):
            errors.append('catalog.plans: every entry must be an object')

    plan_ids: set[str] = set()
    aliases: dict[str, str] = {}
    billing_env_vars: dict[str, str] = {}
    for index, plan in enumerate(plans):
        path = f'catalog.plans[{index}]'
        _unexpected_keys(plan, PLAN_KEYS, path, errors)
        plan_id = plan.get('id')
        if not isinstance(plan_id, str) or not PLAN_ID_RE.fullmatch(plan_id):
            errors.append(f'{path}.id: invalid plan ID {plan_id!r}')
            continue
        if plan_id in plan_ids:
            errors.append(f'{path}.id: duplicate plan ID {plan_id!r}')
        plan_ids.add(plan_id)
        if not isinstance(plan.get('display_name'), str) or not plan.get('display_name'):
            errors.append(f'{path}.display_name: expected a non-empty string')
        if plan.get('lifecycle') not in LIFECYCLES:
            errors.append(f'{path}.lifecycle: expected one of {sorted(LIFECYCLES)}')
        if not isinstance(plan.get('is_paid'), bool):
            errors.append(f'{path}.is_paid: expected a boolean')
        storefronts = plan.get('storefronts')
        if not isinstance(storefronts, list) or len(storefronts) != len(set(storefronts)):
            errors.append(f'{path}.storefronts: expected a unique list')
        elif not set(storefronts).issubset(STOREFRONTS):
            errors.append(f'{path}.storefronts: unknown storefronts {sorted(set(storefronts) - STOREFRONTS)}')
        wire_aliases = plan.get('wire_aliases')
        if not isinstance(wire_aliases, list):
            errors.append(f'{path}.wire_aliases: expected a list')
        else:
            for alias in wire_aliases:
                if not isinstance(alias, str) or not PLAN_ID_RE.fullmatch(alias):
                    errors.append(f'{path}.wire_aliases: invalid alias {alias!r}')
                elif alias in aliases:
                    errors.append(f'{path}.wire_aliases: alias {alias!r} already maps to {aliases[alias]!r}')
                else:
                    aliases[alias] = plan_id
        if plan.get('desktop_profile') not in desktop_profiles:
            errors.append(f'{path}.desktop_profile: unknown desktop profile {plan.get("desktop_profile")!r}')
        conditionals = plan.get('conditional_desktop_profiles')
        if not isinstance(conditionals, list):
            errors.append(f'{path}.conditional_desktop_profiles: expected a list')
        else:
            for conditional_index, conditional in enumerate(conditionals):
                conditional_path = f'{path}.conditional_desktop_profiles[{conditional_index}]'
                if not isinstance(conditional, dict):
                    errors.append(f'{conditional_path}: expected an object')
                    continue
                _unexpected_keys(conditional, {'condition', 'profile'}, conditional_path, errors)
                if not isinstance(conditional.get('condition'), str) or not conditional.get('condition'):
                    errors.append(f'{conditional_path}.condition: expected a non-empty string')
                if conditional.get('profile') not in desktop_profiles:
                    errors.append(f'{conditional_path}.profile: unknown desktop profile')
        if plan.get('fair_use_profile') not in fair_use_profiles:
            errors.append(f'{path}.fair_use_profile: unknown fair-use profile {plan.get("fair_use_profile")!r}')
        if plan.get('phone_calls_profile') not in phone_call_profiles:
            errors.append(f'{path}.phone_calls_profile: unknown phone-call profile {plan.get("phone_calls_profile")!r}')
        _validate_allocations(plan.get('allocations'), f'{path}.allocations', decisions, errors)
        _validate_billing(plan.get('billing'), f'{path}.billing', bool(plan.get('is_paid')), errors)
        billing = plan.get('billing')
        if isinstance(billing, dict):
            for price in billing.get('prices', []):
                if not isinstance(price, dict):
                    continue
                for env_var in price.get('accepted_env_vars', []):
                    if not isinstance(env_var, str):
                        continue
                    prior_plan = billing_env_vars.get(env_var)
                    if prior_plan is not None and prior_plan != plan_id:
                        errors.append(
                            f'{path}.billing: environment variable {env_var} is already owned by {prior_plan!r}'
                        )
                    billing_env_vars[env_var] = plan_id

    if 'basic' not in plan_ids:
        errors.append('catalog.plans: basic is required')
    if set(aliases).intersection(plan_ids):
        errors.append(f'catalog.plans: aliases collide with plan IDs: {sorted(set(aliases).intersection(plan_ids))}')
    for index, plan in enumerate(plans):
        fallback = plan.get('wire_fallback_plan')
        if fallback is not None and fallback not in plan_ids:
            errors.append(f'catalog.plans[{index}].wire_fallback_plan: unknown plan {fallback!r}')
        elif fallback == plan.get('id'):
            errors.append(f'catalog.plans[{index}].wire_fallback_plan: a plan cannot fall back to itself')

    price_entries = catalog.get('recognized_stripe_prices')
    seen_prices: dict[str, tuple[str, str]] = {}
    if not isinstance(price_entries, list):
        errors.append('catalog.recognized_stripe_prices: expected a list')
    else:
        for index, entry in enumerate(price_entries):
            path = f'catalog.recognized_stripe_prices[{index}]'
            if not isinstance(entry, dict):
                errors.append(f'{path}: expected an object')
                continue
            _unexpected_keys(entry, {'price_id', 'plan_id', 'interval', 'environment'}, path, errors)
            price_id = entry.get('price_id')
            plan_id = entry.get('plan_id')
            interval = entry.get('interval')
            if not isinstance(price_id, str) or not STRIPE_PRICE_ID_RE.fullmatch(price_id):
                errors.append(f'{path}.price_id: invalid Stripe price ID')
                continue
            if plan_id not in plan_ids:
                errors.append(f'{path}.plan_id: unknown plan {plan_id!r}')
            elif not _plan_map(catalog)[str(plan_id)].get('is_paid'):
                errors.append(f'{path}.plan_id: Stripe prices cannot map to free plan {plan_id!r}')
            if interval not in INTERVALS:
                errors.append(f'{path}.interval: expected month or year')
            mapping = (str(plan_id), str(interval))
            if price_id in seen_prices:
                errors.append(f'{path}.price_id: duplicate {price_id}; already mapped to {seen_prices[price_id]}')
            else:
                seen_prices[price_id] = mapping
            if entry.get('environment') not in {'dev', 'prod'}:
                errors.append(f'{path}.environment: expected dev or prod')

    product_entries = catalog.get('recognized_stripe_products')
    seen_products: dict[str, str] = {}
    if not isinstance(product_entries, list):
        errors.append('catalog.recognized_stripe_products: expected a list')
    else:
        for index, entry in enumerate(product_entries):
            path = f'catalog.recognized_stripe_products[{index}]'
            if not isinstance(entry, dict):
                errors.append(f'{path}: expected an object')
                continue
            _unexpected_keys(entry, {'product_id', 'plan_id'}, path, errors)
            product_id = entry.get('product_id')
            plan_id = entry.get('plan_id')
            if not isinstance(product_id, str) or not STRIPE_PRODUCT_ID_RE.fullmatch(product_id):
                errors.append(f'{path}.product_id: invalid Stripe product ID')
                continue
            if plan_id not in plan_ids:
                errors.append(f'{path}.plan_id: unknown plan {plan_id!r}')
            elif not _plan_map(catalog)[str(plan_id)].get('is_paid'):
                errors.append(f'{path}.plan_id: Stripe products cannot map to free plan {plan_id!r}')
            if product_id in seen_products:
                errors.append(
                    f'{path}.product_id: duplicate {product_id}; already mapped to {seen_products[product_id]}'
                )
            else:
                seen_products[product_id] = str(plan_id)

    for float_path in _find_floats(catalog):
        errors.append(f'{float_path}: floats are forbidden; use exact integer minor units')
    return errors


def _plan_map(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(plan['id']): plan
        for plan in catalog.get('plans', [])
        if isinstance(plan, dict) and isinstance(plan.get('id'), str)
    }


def _recognized_product_map(catalog: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(entry['product_id']): str(entry['plan_id'])
        for entry in catalog.get('recognized_stripe_products', [])
        if isinstance(entry, dict) and {'product_id', 'plan_id'}.issubset(entry)
    }


def _recognized_price_map(catalog: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        str(entry['price_id']): (str(entry['plan_id']), str(entry['interval']))
        for entry in catalog.get('recognized_stripe_prices', [])
        if isinstance(entry, dict) and {'price_id', 'plan_id', 'interval'}.issubset(entry)
    }


def validate_compatibility(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    """Reject destructive changes to persisted identity and Stripe recognition."""

    errors: list[str] = []
    previous_revision = previous.get('catalog_revision')
    current_revision = current.get('catalog_revision')
    if isinstance(previous_revision, int) and isinstance(current_revision, int):
        if current_revision < previous_revision:
            errors.append('compatibility: catalog_revision cannot decrease')
        elif canonical_json(previous) != canonical_json(current) and current_revision == previous_revision:
            errors.append('compatibility: catalog_revision must increase when the catalog changes')
    previous_plans = _plan_map(previous)
    current_plans = _plan_map(current)
    for plan_id in sorted(set(previous_plans) - set(current_plans)):
        errors.append(f'compatibility: plan {plan_id!r} cannot be removed; deprecate it in place')

    previous_aliases = {
        str(alias): plan_id for plan_id, plan in previous_plans.items() for alias in plan.get('wire_aliases', [])
    }
    current_aliases = {
        str(alias): plan_id for plan_id, plan in current_plans.items() for alias in plan.get('wire_aliases', [])
    }
    for alias, plan_id in sorted(previous_aliases.items()):
        if current_aliases.get(alias) != plan_id:
            errors.append(f'compatibility: wire alias {alias!r} must keep mapping to {plan_id!r}')

    current_prices = _recognized_price_map(current)
    for price_id, mapping in sorted(_recognized_price_map(previous).items()):
        if price_id not in current_prices:
            errors.append(f'compatibility: recognized Stripe price {price_id} cannot be removed')
        elif current_prices[price_id] != mapping:
            errors.append(
                f'compatibility: recognized Stripe price {price_id} cannot change from {mapping} to {current_prices[price_id]}'
            )

    current_products = _recognized_product_map(current)
    for product_id, plan_id in sorted(_recognized_product_map(previous).items()):
        if product_id not in current_products:
            errors.append(f'compatibility: recognized Stripe product {product_id} cannot be removed')
        elif current_products[product_id] != plan_id:
            errors.append(
                f'compatibility: recognized Stripe product {product_id} cannot change from {plan_id!r} '
                f'to {current_products[product_id]!r}'
            )
    return errors


def _is_scannable_source(path: Path) -> bool:
    if path.suffix not in SOURCE_EXTENSIONS and not path.name.startswith('Dockerfile'):
        return False
    relative = path.relative_to(ROOT)
    if any(part in SOURCE_SCAN_EXCLUDED_PARTS for part in relative.parts):
        return False
    return path not in {CATALOG_PATH, GENERATED_PATH}


def scan_embedded_stripe_ids(catalog: Mapping[str, Any]) -> list[str]:
    """Require every production-source Stripe object literal to belong to the catalog."""

    known_prices = set(_recognized_price_map(catalog))
    known_products = set(_recognized_product_map(catalog))
    errors: list[str] = []
    for directory, directory_names, file_names in os.walk(ROOT):
        directory_names[:] = sorted(name for name in directory_names if name not in SOURCE_SCAN_EXCLUDED_PARTS)
        for file_name in sorted(file_names):
            path = Path(directory) / file_name
            if not _is_scannable_source(path):
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            relative = path.relative_to(ROOT).as_posix()
            for price_id in sorted(set(EMBEDDED_PRICE_ID_RE.findall(text)) - known_prices):
                errors.append(f'{relative}: embedded Stripe price {price_id} is absent from plan_catalog.json')
            for product_id in sorted(set(EMBEDDED_PRODUCT_ID_RE.findall(text)) - known_products):
                errors.append(f'{relative}: embedded Stripe product {product_id} is absent from plan_catalog.json')
    return errors


def _python_literal(value: Any) -> str:
    return pprint.pformat(value, width=120, sort_dicts=False)


def render_generated(catalog: Mapping[str, Any]) -> str:
    plans = list(_plan_map(catalog).values())
    plan_ids = [str(plan['id']) for plan in plans]
    aliases = {str(alias): str(plan['id']) for plan in plans for alias in plan.get('wire_aliases', [])}
    paid = [str(plan['id']) for plan in plans if plan.get('is_paid')]
    mobile = [str(plan['id']) for plan in plans if {'android', 'ios'}.intersection(set(plan.get('storefronts', [])))]
    desktop_profiles = catalog['allocation_profiles']['desktop']
    desktop_entitled = [
        str(plan['id'])
        for plan in plans
        if desktop_profiles.get(plan.get('desktop_profile'), {}).get('full_desktop') is True
    ]
    unlimited_transcription = [
        str(plan['id'])
        for plan in plans
        if plan.get('is_paid')
        and plan.get('allocations', {}).get('transcription', {}).get('limit', {}).get('kind') == 'unlimited'
    ]
    wire_fallbacks = {
        str(plan['id']): str(plan['wire_fallback_plan']) for plan in plans if plan.get('wire_fallback_plan') is not None
    }
    legacy_wire_values = [plan_id for plan_id in plan_ids if plan_id not in wire_fallbacks]
    display_names = {str(plan['id']): str(plan['display_name']) for plan in plans}
    storefronts = {str(plan['id']): tuple(plan.get('storefronts', [])) for plan in plans}
    plan_data = {str(plan['id']): plan for plan in plans}
    recognized_prices = {
        price_id: plan_and_interval[0] for price_id, plan_and_interval in _recognized_price_map(catalog).items()
    }
    recognized_price_intervals = {
        price_id: plan_and_interval[1] for price_id, plan_and_interval in _recognized_price_map(catalog).items()
    }
    recognized_products = _recognized_product_map(catalog)
    env_var_plans: dict[str, str] = {}
    primary_env_vars: dict[str, dict[str, str]] = {}
    for plan in plans:
        plan_id = str(plan['id'])
        billing = plan.get('billing')
        if not isinstance(billing, dict):
            continue
        primary_env_vars[plan_id] = {}
        for price in billing.get('prices', []):
            interval = str(price['interval'])
            primary_env_vars[plan_id][interval] = str(price['primary_env_var'])
            for env_var in price.get('accepted_env_vars', []):
                env_var_plans[str(env_var)] = plan_id

    profiles = catalog['allocation_profiles']
    enum_lines = '\n'.join(f"    {plan_id} = {plan_id!r}" for plan_id in plan_ids)
    alias_lines = '\n'.join(f"    {alias!r}: PlanType.{plan_id}," for alias, plan_id in aliases.items())

    def enum_set(values: list[str]) -> str:
        if not values:
            return 'frozenset()'
        members = ', '.join(f'PlanType.{value}' for value in values)
        return f'frozenset({{{members}}})'

    def enum_map(values: Mapping[str, str]) -> str:
        if not values:
            return '{}'
        lines = ',\n'.join(f'    PlanType.{key}: PlanType.{value}' for key, value in values.items())
        return '{\n' + lines + ',\n}'

    def enum_value_map(values: Mapping[str, Any]) -> str:
        lines = ',\n'.join(f'    PlanType.{key}: {_python_literal(value)}' for key, value in values.items())
        return '{\n' + lines + ',\n}'

    recognized_price_lines = ',\n'.join(
        f'    {price_id!r}: PlanType.{plan_id}' for price_id, plan_id in recognized_prices.items()
    )
    recognized_product_lines = ',\n'.join(
        f'    {product_id!r}: PlanType.{plan_id}' for product_id, plan_id in recognized_products.items()
    )
    env_var_lines = ',\n'.join(f'    {env_var!r}: PlanType.{plan_id}' for env_var, plan_id in env_var_plans.items())
    primary_env_lines = ',\n'.join(
        f'    PlanType.{plan_id}: {_python_literal(intervals)}' for plan_id, intervals in primary_env_vars.items()
    )

    return f'''# Generated by backend/scripts/generate_plan_catalog.py from backend/config/plan_catalog.json.
# Do not edit by hand.
# fmt: off

from __future__ import annotations

from enum import Enum
from typing import Any, Final


class PlanType(str, Enum):
{enum_lines}

    @classmethod
    def _missing_(cls, value: object):
        return WIRE_PLAN_ALIASES.get(value) if isinstance(value, str) else None


WIRE_PLAN_ALIASES: Final[dict[str, PlanType]] = {{
{alias_lines}
}}

CATALOG_SHA256: Final = {catalog_digest(catalog)!r}
CATALOG_REVISION: Final = {catalog['catalog_revision']!r}
CATALOG_AUTHORITY: Final = {_python_literal(catalog['authority'])}
OPEN_PLAN_DECISIONS: Final = {_python_literal(catalog['open_decisions'])}
MEASUREMENT_CONTRACTS: Final = {_python_literal(catalog['measurement_contracts'])}
PLAN_CATALOG_DATA: Final[dict[str, dict[str, Any]]] = {_python_literal(plan_data)}
PLAN_TYPE_VALUES: Final[frozenset[str]] = frozenset({_python_literal(plan_ids)})
PAID_PLAN_TYPES: Final[frozenset[PlanType]] = {enum_set(paid)}
PAID_PLAN_IDS: Final[frozenset[str]] = frozenset(plan.value for plan in PAID_PLAN_TYPES)
MOBILE_PLAN_TYPES: Final[frozenset[PlanType]] = {enum_set(mobile)}
DESKTOP_ENTITLED_PLAN_TYPES: Final[frozenset[PlanType]] = {enum_set(desktop_entitled)}
UNLIMITED_TRANSCRIPTION_PLAN_TYPES: Final[frozenset[PlanType]] = {enum_set(unlimited_transcription)}
WIRE_FALLBACK_PLAN_TYPES: Final[dict[PlanType, PlanType]] = {enum_map(wire_fallbacks)}
LEGACY_WIRE_PLAN_VALUES: Final[tuple[str, ...]] = tuple({_python_literal(legacy_wire_values)})
PLAN_DISPLAY_NAMES: Final[dict[PlanType, str]] = {enum_value_map(display_names)}
PLAN_STOREFRONTS: Final[dict[PlanType, tuple[str, ...]]] = {enum_value_map(storefronts)}
RECOGNIZED_STRIPE_PRICE_PLAN_TYPES: Final[dict[str, PlanType]] = {{
{recognized_price_lines}
}}
RECOGNIZED_STRIPE_PRICE_INTERVALS: Final[dict[str, str]] = {_python_literal(recognized_price_intervals)}
RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES: Final[dict[str, PlanType]] = {{
{recognized_product_lines}
}}
BILLING_ENV_VAR_PLAN_TYPES: Final[dict[str, PlanType]] = {{
{env_var_lines}
}}
PRIMARY_BILLING_ENV_VARS: Final[dict[PlanType, dict[str, str]]] = {{
{primary_env_lines}
}}
DESKTOP_PROFILE_DEFAULTS: Final[dict[str, dict[str, Any]]] = {_python_literal(profiles['desktop'])}
FAIR_USE_PROFILE_LIMITS: Final[dict[str, dict[str, Any]]] = {_python_literal(profiles['fair_use'])}
PHONE_CALL_PROFILE_DEFAULTS: Final[dict[str, dict[str, Any]]] = {_python_literal(profiles['phone_calls'])}


__all__ = [
    'BILLING_ENV_VAR_PLAN_TYPES',
    'CATALOG_AUTHORITY',
    'CATALOG_REVISION',
    'CATALOG_SHA256',
    'DESKTOP_ENTITLED_PLAN_TYPES',
    'DESKTOP_PROFILE_DEFAULTS',
    'FAIR_USE_PROFILE_LIMITS',
    'LEGACY_WIRE_PLAN_VALUES',
    'MEASUREMENT_CONTRACTS',
    'MOBILE_PLAN_TYPES',
    'OPEN_PLAN_DECISIONS',
    'PAID_PLAN_IDS',
    'PAID_PLAN_TYPES',
    'PHONE_CALL_PROFILE_DEFAULTS',
    'PLAN_CATALOG_DATA',
    'PLAN_DISPLAY_NAMES',
    'PLAN_STOREFRONTS',
    'PLAN_TYPE_VALUES',
    'PRIMARY_BILLING_ENV_VARS',
    'PlanType',
    'RECOGNIZED_STRIPE_PRICE_INTERVALS',
    'RECOGNIZED_STRIPE_PRICE_PLAN_TYPES',
    'RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES',
    'UNLIMITED_TRANSCRIPTION_PLAN_TYPES',
    'WIRE_FALLBACK_PLAN_TYPES',
    'WIRE_PLAN_ALIASES',
]
'''


def validate_publishable_catalog(catalog: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for plan_id, plan in _plan_map(catalog).items():
        for allocation_name, allocation in plan.get('allocations', {}).items():
            limit = allocation.get('limit', {})
            if limit.get('kind') == 'decision_required':
                errors.append(f'publishable: {plan_id}.{allocation_name} still requires {limit.get("decision_id")}')
            exhaustion = allocation.get('exhaustion', {})
            if exhaustion.get('kind') == 'decision_required':
                errors.append(
                    f'publishable: {plan_id}.{allocation_name} still requires {exhaustion.get("decision_id")}'
                )
    for allocation_name, contract in catalog.get('measurement_contracts', {}).items():
        if not isinstance(contract, dict) or contract.get('cost_status') != 'complete':
            errors.append(f'publishable: {allocation_name} cost accounting is not complete')
    return errors


def load_catalog_from_git(ref: str) -> Mapping[str, Any] | None:
    result = subprocess.run(
        ['git', 'show', f'{ref}:{CATALOG_REPO_PATH}'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        missing_markers = ('does not exist', 'exists on disk, but not in', 'Path \'')
        if any(marker in result.stderr for marker in missing_markers):
            return None
        raise RuntimeError(f'could not read {CATALOG_REPO_PATH} from {ref}: {result.stderr.strip()}')
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError(f'{CATALOG_REPO_PATH} at {ref} is not an object')
    return value


def _print_errors(errors: Iterable[str]) -> int:
    values = list(errors)
    if not values:
        return 0
    print('plan catalog validation failed:', file=sys.stderr)
    for error in values:
        print(f'- {error}', file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the generated Python projection is stale.')
    parser.add_argument('--base-ref', help='Git ref whose irreversible identity/Stripe mappings must be retained.')
    parser.add_argument(
        '--require-publishable', action='store_true', help='Reject unresolved policy and legacy billing.'
    )
    parser.add_argument('--skip-source-scan', action='store_true', help='Test-only escape for isolated fixture roots.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = load_catalog()
    errors = validate_catalog(catalog)
    if not args.skip_source_scan:
        errors.extend(scan_embedded_stripe_ids(catalog))
    if args.base_ref:
        previous = load_catalog_from_git(args.base_ref)
        if previous is not None:
            errors.extend(validate_compatibility(previous, catalog))
        # `previous is None` means the base predates the catalog, so there is nothing to
        # compare and the append-only/identity guard silently does not run. That is correct
        # for the PR that introduces the catalog, and only for that PR: from the first merge
        # onward a None here means the base ref is wrong, not that the ledger is safe. Do
        # not read a green run on an ancestor-less base as evidence the ledger was checked.
    if args.require_publishable:
        errors.extend(validate_publishable_catalog(catalog))
    if errors:
        return _print_errors(errors)

    generated = render_generated(catalog)
    if args.check:
        current = GENERATED_PATH.read_text(encoding='utf-8') if GENERATED_PATH.exists() else ''
        if current != generated:
            print(f'{GENERATED_PATH.relative_to(ROOT)} is stale; regenerate it with this script.', file=sys.stderr)
            diff = difflib.unified_diff(
                current.splitlines(),
                generated.splitlines(),
                fromfile=str(GENERATED_PATH.relative_to(ROOT)),
                tofile='expected',
                lineterm='',
            )
            for line in list(diff)[:200]:
                print(line, file=sys.stderr)
            return 1
        print(f'plan catalog is valid and {GENERATED_PATH.relative_to(ROOT)} is current')
        return 0

    GENERATED_PATH.write_text(generated, encoding='utf-8')
    print(f'wrote {GENERATED_PATH.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
