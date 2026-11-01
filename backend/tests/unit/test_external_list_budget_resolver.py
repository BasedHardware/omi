"""One owner-aware resolver without changing existing request/env overrides."""

from types import SimpleNamespace

import pytest
from utils.other import list_budget as budgets


@pytest.mark.parametrize('raw,expected', [(None, 25000), ('bad', 25000), ('0', 25000), ('-1', 25000), ('17', 17)])
def test_document_resolver_keeps_released_env_fallback(monkeypatch, raw, expected):
    monkeypatch.delenv('OMI_LIST_READ_MAX_DOCUMENTS', raising=False)
    monkeypatch.delenv('OMI_LIST_READ_BUDGET_SECONDS', raising=False)
    monkeypatch.delenv('HTTP_GET_TIMEOUT', raising=False)
    if raw is not None:
        monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', raw)
    context = SimpleNamespace(uid='owner', app_id='app', key_id='key')
    request = SimpleNamespace(state=SimpleNamespace(omi_request_started_monotonic=95.0))
    budget = budgets.list_read_budget_for_request(
        request, route='api', owner_uid='owner', context=context, clock=lambda: 100.0
    )
    assert budget.max_documents == expected
    assert budget.remaining_seconds == 19.0  # 24 seconds, still request-start anchored.


def test_factory_injects_owner_context_once_and_explicit_overrides_stay_authoritative(monkeypatch):
    context = SimpleNamespace(uid='owner', app_id='app', key_id='key')
    seen = []

    def resolve(*, owner_uid=None, context=None):
        seen.append((owner_uid, context))
        return 7

    monkeypatch.setattr(budgets, 'resolve_list_read_max_documents', resolve)
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '2')
    budget = budgets.list_read_budget_for_request(
        None, route='api', owner_uid='owner', context=context, clock=lambda: 100.0
    )
    assert budget.max_documents == 7 and budget.remaining_seconds == 2
    assert seen == [('owner', context)]
    explicit = budgets.list_read_budget_for_request(None, route='api', max_documents=9, seconds=3, clock=lambda: 100.0)
    assert explicit.max_documents == 9 and explicit.remaining_seconds == 3
    assert len(seen) == 1
