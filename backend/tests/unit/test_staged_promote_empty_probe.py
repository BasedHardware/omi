"""Real promote route/projection with counted offline Firestore queries."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.candidate import CandidateRecord
from models.task_intelligence import TaskWorkflowControl
from routers import staged_tasks as route
from tests.unit.test_external_list_nested_budget import Store
from utils.observability.external_lists import (
    EXTERNAL_LIST_HTTP_TOTAL,
    ExternalListMetricsMiddleware,
    STAGED_PROMOTE_ROUTE,
)
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
EMPTY = b'{"promoted":false,"reason":"No staged tasks available","promoted_task":null}'


def candidate(status='pending', generation=7):
    proposal = proposal_from_legacy_staged({'id': 'legacy', 'description': 'A task'})
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id='canonical',
        account_generation=generation,
        idempotency_key='offline-test',
        status=status,
        created_at=NOW,
        resolved_at=NOW if status != 'pending' else None,
        resolution_reason=status if status != 'pending' else None,
        result_task_id='existing-task' if status == 'accepted' else None,
    ).model_dump(mode='python')


@pytest.fixture
def serving(monkeypatch):
    store = Store({})
    monkeypatch.setattr(route.staged_tasks_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(route.staged_tasks_db, 'db', store)
    monkeypatch.setattr(route.candidates_db, 'db', store)
    monkeypatch.setattr(route.task_control_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(route, 'load_compatibility_candidates', lambda uid, generation, loader: loader())
    monkeypatch.delenv('OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED', raising=False)
    store.rows['users/owner/task_intelligence_control/state'] = TaskWorkflowControl(account_generation=7).model_dump()
    app = FastAPI()
    app.include_router(route.router)
    app.add_middleware(ExternalListMetricsMiddleware)
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: 'owner'
    selected = Mock(return_value={'promoted': True, 'reason': None, 'promoted_task': None})
    monkeypatch.setattr(route, 'promote_staged_task_by_id', selected)
    return TestClient(app), store, selected


def billed(store):
    # Firestore charges one minimum read for empty query results; point reads
    # are counted by Store even on misses. Keep this distinct from result rows.
    return store.physical + sum(count == 0 for _, _, _, count in store.windows)


def reset(store):
    store.physical = store.streams = store.batch_gets = 0
    store.windows.clear()


def test_empty_stores_skip_control_and_projection_with_identical_bytes(serving, monkeypatch):
    client, store, selected = serving
    counter = EXTERNAL_LIST_HTTP_TOTAL.labels(route=STAGED_PROMOTE_ROUTE, outcome='success')
    before = counter._value.get()
    on = client.post(STAGED_PROMOTE_ROUTE)
    assert on.status_code == 200 and on.content == EMPTY
    assert store.streams == 2 and store.physical == 0 and billed(store) == 2
    assert all(window[2] == 1 and not window[1] for window in store.windows)
    selected.assert_not_called()
    assert counter._value.get() == before + 1
    reset(store)
    monkeypatch.setenv('OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED', ' FaLsE ')
    off = client.post(STAGED_PROMOTE_ROUTE)
    assert off.content == on.content
    assert store.streams == 2 and store.physical == 1 and billed(store) == 3
    print('empty promote: on=2 empty probes/0 rows/2 modeled billed reads; off=1 control+2 empty scans/3 billed reads')


@pytest.mark.parametrize(
    'kind',
    [
        'legacy_missing_fields',
        'completed',
        'hidden_legacy',
        'rejected_suppresses_legacy',
        'candidate',
        'accepted_suppresses_legacy',
        'other_generation',
        'malformed_candidate',
    ],
)
def test_any_physical_row_preserves_full_projection_and_selection(serving, monkeypatch, kind):
    client, store, selected = serving
    if kind in {
        'legacy_missing_fields',
        'completed',
        'hidden_legacy',
        'accepted_suppresses_legacy',
        'rejected_suppresses_legacy',
    }:
        # No created_at, updated_at, relevance_score or completed field on the
        # legacy active row: a field predicate/order would falsely hide it.
        store.rows['users/owner/staged_tasks/legacy'] = {'description': 'A task'}
        if kind == 'hidden_legacy':
            store.rows['users/owner/staged_tasks/legacy']['hidden'] = True
        if kind == 'completed':
            store.rows['users/owner/staged_tasks/legacy']['completed'] = True
    if kind in {'candidate', 'accepted_suppresses_legacy', 'rejected_suppresses_legacy', 'other_generation'}:
        store.rows['users/owner/candidates/canonical'] = candidate(
            status=(
                'accepted'
                if kind == 'accepted_suppresses_legacy'
                else 'rejected' if kind == 'rejected_suppresses_legacy' else 'pending'
            ),
            generation=8 if kind == 'other_generation' else 7,
        )
    if kind == 'malformed_candidate':
        store.rows['users/owner/candidates/broken'] = {'status': 'pending'}
    on = client.post(STAGED_PROMOTE_ROUTE)
    assert on.status_code == 200
    on_selection = selected.call_args_list[:]
    on_reads, on_queries = billed(store), store.streams
    assert any(window[2] == 1 for window in store.windows)
    selected.reset_mock()
    reset(store)
    monkeypatch.setenv('OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED', 'false')
    off = client.post(STAGED_PROMOTE_ROUTE)
    assert off.status_code == 200 and off.content == on.content
    assert selected.call_args_list == on_selection
    assert on_reads - billed(store) in (1, 2)
    assert on_queries - store.streams in (1, 2)
    if kind in {'legacy_missing_fields', 'hidden_legacy', 'candidate'}:
        selected.assert_called_once_with('canonical' if kind == 'candidate' else 'legacy', uid='owner')
    else:
        assert off.content == EMPTY
        selected.assert_not_called()


def test_probe_outage_uses_original_reader_and_records_fallback(serving, monkeypatch):
    client, store, _ = serving
    probe = Mock(side_effect=RuntimeError('offline probe failure'))
    fallback = Mock()
    monkeypatch.setattr(route.staged_tasks_db, 'staged_task_stores_physically_empty', probe)
    monkeypatch.setattr(route, 'record_fallback', fallback)
    response = client.post(STAGED_PROMOTE_ROUTE)
    assert response.status_code == 200 and response.content == EMPTY
    assert billed(store) == 3
    fallback.assert_called_once()


@pytest.mark.parametrize('value', ['', '0', 'true', 'off'])
def test_probe_is_on_unless_false(serving, monkeypatch, value):
    client, store, _ = serving
    monkeypatch.setenv('OMI_STAGED_TASK_PROMOTE_EMPTY_PROBE_ENABLED', value)
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    assert store.physical == 0 and billed(store) == 2


def test_promote_auth_failure_is_measured_before_probe(serving):
    client, store, _ = serving

    def unauthorized():
        raise HTTPException(401)

    client.app.dependency_overrides[route.auth.get_current_user_uid] = unauthorized
    counter = EXTERNAL_LIST_HTTP_TOTAL.labels(route=STAGED_PROMOTE_ROUTE, outcome='auth_error')
    before = counter._value.get()
    assert client.post(STAGED_PROMOTE_ROUTE).status_code == 401
    assert counter._value.get() == before + 1
    assert store.streams == store.physical == 0
    assert client.get(STAGED_PROMOTE_ROUTE).status_code == 405
    assert counter._value.get() == before + 1  # Only the exact POST is measured.
