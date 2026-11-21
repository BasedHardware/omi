"""Recheck paid dispatches after current-ledger writes, before factories or claims."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

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


def test_default_off_scope_never_reads_allowance(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    lookup = Mock(side_effect=AssertionError('flag-off admission read'))
    monkeypatch.setattr(funded, 'allowance', lookup)
    with generated.generated_compute_scope('u'):
        assert funded.processing_allowed('u')
        assert generated.generated_compute_allowed('u', 'conv_folder', allow_byok=False)
    lookup.assert_not_called()


@pytest.mark.parametrize('flag', ['STT_CAP_DISPATCH_ENFORCEMENT'])
def test_backlog_consent_expires_between_dispatches_without_affecting_new_capture(monkeypatch, flag):
    from utils import stt_cap_dispatch as stt

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv(flag, 'true')
    month = ['2026-01']
    monkeypatch.setattr(funded, 'period_id', lambda: month[0])
    allowance = Mock(return_value=SimpleNamespace(managed=True))
    monkeypatch.setattr(funded, 'allowance', allowance)
    monkeypatch.setattr(stt, 'funded_allowance', allowance)
    with funded.backlog_consent('u', '2026-01'):
        assert funded.processing_allowed('u')
        assert stt.sync_allowed('u')
        month[0] = '2026-02'
        before = allowance.call_count
        assert not funded.processing_allowed('u')
        assert not generated.generated_compute_allowed('u', 'title', allow_byok=True)
        assert not stt.sync_allowed('u')
        assert allowance.call_count == before  # Expired grant cannot spend/read new budget.
        assert not funded.consent_allows('other-user')
    # Fresh recordings have no inherited backlog grant and use the new allowance.
    assert funded.processing_allowed('u')
    assert stt.sync_allowed('u')


def test_disabled_backlog_consent_is_inert(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setattr(funded, 'period_id', Mock(side_effect=AssertionError('off-path month read')))
    with funded.backlog_consent('u', 'old'):
        assert funded.consent_allows('u') and funded.processing_allowed('u')
