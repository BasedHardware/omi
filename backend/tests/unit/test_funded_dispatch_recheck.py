"""Recheck paid dispatches after current-ledger writes, before factories or claims."""

import ast
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from config import ladder_v1 as policy
from config.rate_card import budget_units
from database import funded_usage_session, usage_units, usage_units_session, users as users_db
from tests.unit.fixtures.shadow_usage_firestore import Store
from utils import byok, funded_processing as funded, generated_compute as generated, ladder_v1

BACKEND = Path(__file__).resolve().parents[2]


def _entrypoint(path, name, namespace):
    """Execute the actual entrypoint without importing the provider/router graph."""
    tree = ast.parse((BACKEND / path).read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.returns = None
    for argument in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
        argument.annotation = None
    ast.fix_missing_locations(function)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(BACKEND / path), 'exec'), namespace)
    return namespace[name]


def _hourly(micro_units):
    return {
        'year': 2026,
        'month': 10,
        'shadow_v1': {'features': {'transcription': {'funding': {'omi': {'micro_units': micro_units}}}}},
    }


@pytest.mark.parametrize('ledger', ['hourly', 'gateway', 'api'])
def test_later_factory_in_nested_scope_rechecks_open_ledgers_without_rescanning_month(monkeypatch, ledger):
    moment = datetime(2026, 10, 17, 10, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(ladder_v1, 'datetime', Clock)
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', lambda *args, **kwargs: None)
    # Start just below the real Basic budget, with usage in a closed bucket.
    budget = budget_units(policy.entitlements(None))
    store = Store({'users/u/hourly_usage/2026-10-01-00': _hourly((budget - 1) * 1_000_000)})
    monkeypatch.setattr(funded_usage_session, 'get_customer_firestore_client', lambda: store)
    # The projection receives this client through its normal lazy getter.
    monkeypatch.setattr(usage_units, 'get_customer_firestore_client', lambda: store)
    monkeypatch.setattr(funded_usage_session, '_sessions', funded_usage_session.OrderedDict())
    month_read = Mock(wraps=usage_units_session.read_usage_month)
    monkeypatch.setattr(usage_units_session, 'read_usage_month', month_read)

    provider_factory = Mock(return_value=object())
    namespace = {
        'require_current_generated_compute': generated.require_current_generated_compute,
        'get_or_create_omi_gateway_llm': provider_factory,
        'CHAT_STRUCTURED_AUTO_LANE_ID': 'test-lane',
        'BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS': 1,
    }
    _entrypoint('utils/llm/clients.py', '_require_client_budget', namespace)
    factory = _entrypoint('utils/llm/clients.py', 'get_llm_gateway_chat_structured', namespace)
    with generated.generated_compute_scope('u'):
        factory()
        assert provider_factory.call_count == 1
        assert month_read.call_count == 1
        before = store.reads
        if ledger == 'hourly':
            store.docs['users/u/hourly_usage/2026-10-17-10'] = _hourly(1_000_000)
        elif ledger == 'gateway':
            key = 'llm_gateway_user_days/2026-10-17_' + sha256(b'u').hexdigest()[:16]
            store.docs[key] = {
                'shadow_v1': {'hours': {'10': {'features': {'chat': {'funding': {'omi': {'micro_units': 1_000_000}}}}}}}
            }
        else:
            store.docs['users/u/ladder_v1_api_days/2026-10-17'] = {'micro_units': 1_000_000, 'requests': 1}
        with pytest.raises(HTTPException) as raised:
            factory()
        assert raised.value.status_code == 402
        assert raised.value.detail['error'] == 'usage_budget_exhausted'
        assert provider_factory.call_count == 1
        assert store.reads - before == 3  # Open hour, gateway day, API day only.
        assert month_read.call_count == 1


@pytest.mark.parametrize('flag', ['STT_CAP_DISPATCH_ENFORCEMENT', 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', None])
@pytest.mark.parametrize('available', [False, True])
def test_first_open_checks_company_funding_before_claim_even_with_validated_byok(monkeypatch, flag, available):
    for switch in ('STT_CAP_DISPATCH_ENFORCEMENT', 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED'):
        monkeypatch.setenv(switch, 'true' if switch == flag else 'false')
    monkeypatch.setattr(byok, 'has_validated_byok_keys', lambda: True)
    monkeypatch.setattr(byok, 'get_byok_uid', lambda: 'u')
    monkeypatch.setattr(byok, 'get_byok_key', lambda provider: 'synthetic-customer-key')
    budget = Mock(return_value=available)
    monkeypatch.setattr(funded, 'processing_allowed', budget)
    claim = Mock(return_value='lease')
    submit = Mock()
    dispatch = _entrypoint(
        'routers/conversations.py',
        '_dispatch_first_open_work',
        {
            'generated_compute_allowed': generated.generated_compute_allowed,
            'conversations_db': SimpleNamespace(claim_authorized_first_open_work=claim),
            'submit_with_context': submit,
            'postprocess_executor': object(),
            'logger': Mock(),
        },
    )
    dispatch('u', {'id': 'conversation', 'source': 'desktop', 'jit_first_open': {'state': 'pending'}})
    if flag is not None and not available:
        claim.assert_not_called()
        submit.assert_not_called()
    else:
        claim.assert_called_once_with('u', 'conversation', 'desktop')
        submit.assert_called_once()
    assert budget.call_count == (flag is not None)


def test_default_off_scope_never_reads_allowance(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    lookup = Mock(side_effect=AssertionError('flag-off admission read'))
    monkeypatch.setattr(funded, 'allowance', lookup)
    with generated.generated_compute_scope('u'):
        assert funded.processing_allowed('u')
        assert generated.generated_compute_allowed('u', 'conv_folder', allow_byok=False)
    lookup.assert_not_called()
