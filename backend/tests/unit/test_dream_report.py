"""Owner-only API and independent transactional manual allowances."""

import asyncio
import json
import time
import httpx
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import DeadlineExceeded

from config.dream_agent import Caps
from database import dream_store, review_store
from database.firestore_retry import FIRESTORE_NO_RETRY
from routers import dream_report as routes
from tests.support import dream_firestore
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_report
from utils.llm.shaped_agent import Turn
from scripts.export_openapi import build_openapi
from scripts.generate_dart_models import build_output

from tests.unit.test_dream_harness_runtime import runtime, store, UID


def test_checked_in_dream_schema_and_mobile_dtos_match_real_routes():
    root = Path(__file__).resolve().parents[3]
    app = FastAPI()
    app.include_router(routes.router)
    spec = json.loads((root / 'backend/docs/api/dream-openapi.json').read_text())
    assert spec == build_openapi(app, 'dream')
    assert (root / 'app/lib/backend/schema/gen/dream_wire.g.dart').read_text() == build_output(spec, 'dream')
    assert 'GeneratedDreamRunRequest({' not in build_output(spec, 'dream')


@pytest.fixture
def client(runtime, monkeypatch):
    monkeypatch.setattr(dream_report, 'get_firestore_client', dream_store.get_firestore_client)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_manual_capacity_wait_is_retryable(client, monkeypatch):
    monkeypatch.setattr(
        dream_agent, 'run_pass', AsyncMock(return_value={'status': 'waiting', 'reason': 'reserved_capacity'})
    )
    response = client.post('/v1/dream/runs', json={})
    assert response.status_code == 503 and response.headers['retry-after'] == '120'


def test_global_kill_closes_owner_reports_before_model_dispatch(client, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    model = AsyncMock()
    monkeypatch.setattr(dream_agent, 'run_pass', model)
    assert client.get('/v1/dream/runs').status_code == 404
    assert client.post('/v1/dream/runs', json={}).status_code == 404
    model.assert_not_called()


@pytest.mark.parametrize(
    'reason,code', [('dream_run_in_progress', 409), ('dream_manual_limit', 429), ('dream_budget_unavailable', 503)]
)
def test_manual_decline_is_not_mistaken_for_idle(client, monkeypatch, reason, code):
    monkeypatch.setattr(dream_agent, 'run_pass', AsyncMock(side_effect=dream_store.AdmissionDenied(reason)))
    assert client.post('/v1/dream/runs', json={}).status_code == code


def test_projection_only_exposes_owner_labels_and_no_seed_refs(runtime, monkeypatch):
    monkeypatch.setattr(
        dream_report.dream_reads, 'read_record', lambda *args, **kwargs: {'structured': {'title': 'Synthetic report'}}
    )
    source = {
        'status': 'complete',
        'tokens': 50,
        'proposed': {
            'edits': [
                {
                    'key': 'synthetic-key',
                    'kind': 'dismiss_person',
                    'target': 'people/junk',
                    'reason': 'Synthetic correction',
                    'evidence': ['conversations/one'],
                    'policy': 'auto',
                }
            ]
        },
        'notes': 'Private synthetic future digest',
        'outcomes': [{'key': 'synthetic-key', 'status': 'applied'}],
    }
    raw = review_store.encode_doc(UID, {'source': source}) | {'created_at': datetime.now(timezone.utc), 'mode': 'on'}
    report = dream_report.project_run(UID, 'synthetic-run', raw)
    text = report.model_dump_json()
    assert 'Private synthetic' not in text and 'people/junk' not in text and 'conversations/one' not in text
    assert report.edits[0].outcome == 'applied'


def seed_owner(runtime, *, passes=1, dirty=0, runs=()):
    """One eligible owner with bounded state, dirty rows, and projected run rows."""
    runtime.rows[('users', UID)] = {}
    runtime.rows[('dream_users', UID)] = {
        'day': datetime.now(timezone.utc).date().isoformat(),
        'passes': passes,
        'manual_runs': 0,
        'score': 0,
    }
    for index in range(dirty):
        runtime.rows[('dream_users', UID, 'dirty', f'dirty-{index}')] = {
            'id': f'dirty-{index}',
            'collection': 'conversations',
            'last_changed_at': datetime.now(timezone.utc),
        }
    for run_id, created_at, targets in runs:
        source = {
            'status': 'complete',
            'proposed': {
                'edits': [
                    {'key': f'{run_id}-{index}', 'kind': 'title', 'target': target, 'reason': 'Synthetic correction'}
                    for index, target in enumerate(targets)
                ]
            },
            'outcomes': [],
        }
        runtime.rows[('users', UID, 'dream_runs', run_id)] = review_store.encode_doc(UID, {'source': source}) | {
            'created_at': created_at,
            'mode': 'on',
        }


def test_get_runs_reports_the_owner_history_without_a_truncation_header(client, runtime, monkeypatch):
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '2')
    now = datetime.now(timezone.utc)
    seed_owner(
        runtime,
        passes=2,
        dirty=2,
        runs=[
            ('newer-run', now, ['conversations/one']),
            ('older-run', now - timedelta(minutes=3), []),
        ],
    )
    monkeypatch.setattr(dream_report.dream_reads, 'read_record', lambda *args, **kwargs: {'structured': {'title': 'T'}})
    response = client.get('/v1/dream/runs')

    assert response.status_code == 200
    assert 'x-omi-list-truncated' not in {key.lower() for key in response.headers}
    body = response.json()
    assert [run['run_id'] for run in body['runs']] == ['newer-run', 'older-run']
    assert body['passes_today'] == 2 and body['queued_changes'] == 2 and body['mode'] == 'on'


def test_stalled_run_stream_returns_the_runs_it_has_with_the_truncation_header(client, runtime, monkeypatch):
    """One slow Firestore op ends the list at the budget, not at the 90 s cutoff."""
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '0.3')
    now = datetime.now(timezone.utc)
    seed_owner(
        runtime,
        runs=[
            ('first-run', now, []),
            ('second-run', now - timedelta(minutes=1), []),
        ],
    )
    monkeypatch.setattr(
        dream_report.dream_reads,
        'read_record',
        lambda *args, **kwargs: pytest.fail('no target read should start after the budget is spent'),
    )
    original_stream = dream_firestore.Query.stream

    def stalled(query, transaction=None, timeout=None, retry=None):
        if query.path[-1] != 'dream_runs':
            return original_stream(query, transaction=transaction, timeout=timeout, retry=retry)
        # Every Firestore call on this path must carry the budget's deadline
        # with retries disabled.
        assert retry is FIRESTORE_NO_RETRY
        assert timeout is not None and 0 < timeout <= 0.3
        rows = list(original_stream(query, transaction=transaction, timeout=timeout, retry=retry))

        def stream():
            yield rows[0]
            time.sleep(0.3)
            raise DeadlineExceeded('simulated stalled query stream')

        return stream()

    monkeypatch.setattr(dream_firestore.Query, 'stream', stalled)
    started = time.monotonic()
    response = client.get('/v1/dream/runs')
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.headers['x-omi-list-truncated'] == 'true'
    # The row that crossed the wire before the stall still ships.
    assert [run['run_id'] for run in response.json()['runs']] == ['first-run']
    assert elapsed < 5


def test_spent_budget_stops_the_sequence_before_any_later_read(client, runtime, monkeypatch):
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '0.25')
    now = datetime.now(timezone.utc)
    seed_owner(runtime, dirty=1, runs=[('only-run', now, ['conversations/one'])])
    target_reads = []
    monkeypatch.setattr(
        dream_report.dream_reads,
        'read_record',
        lambda uid, ref, **kwargs: target_reads.append(ref) or {'structured': {'title': 'T'}},
    )
    streams = []
    original_stream = dream_firestore.Query.stream

    def recording_stream(query, transaction=None, timeout=None, retry=None):
        streams.append(query.path)
        return original_stream(query, transaction=transaction, timeout=timeout, retry=retry)

    monkeypatch.setattr(dream_firestore.Query, 'stream', recording_stream)
    original_get = dream_firestore.Document.get

    def stalled_state(document, transaction=None, **kwargs):
        if document.path == ('dream_users', UID):
            time.sleep(0.3)
            raise DeadlineExceeded('simulated stalled state read')
        return original_get(document, transaction=transaction, **kwargs)

    monkeypatch.setattr(dream_firestore.Document, 'get', stalled_state)
    started = time.monotonic()
    response = client.get('/v1/dream/runs')
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.headers['x-omi-list-truncated'] == 'true'
    body = response.json()
    assert body['runs'] == [] and body['queued_changes'] == 0
    # A spent deadline never starts the run stream, the target reads, or the count.
    assert target_reads == [] and streams == []
    assert elapsed < 5


def test_stalled_eligibility_gate_answers_a_retryable_503(client, runtime, monkeypatch):
    """Eligibility cannot be partially true, so a stalled gate is retryable, never 200/504."""
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '0.25')
    seed_owner(runtime, runs=[('only-run', datetime.now(timezone.utc), [])])
    streams = []
    original_stream = dream_firestore.Query.stream

    def recording_stream(query, transaction=None, timeout=None, retry=None):
        streams.append(query.path)
        return original_stream(query, transaction=transaction, timeout=timeout, retry=retry)

    monkeypatch.setattr(dream_firestore.Query, 'stream', recording_stream)
    original_get = dream_firestore.Document.get

    def stalled_gate(document, transaction=None, **kwargs):
        if document.path == ('users', UID):
            time.sleep(0.3)
            raise DeadlineExceeded('simulated stalled eligibility read')
        return original_get(document, transaction=transaction, **kwargs)

    monkeypatch.setattr(dream_firestore.Document, 'get', stalled_gate)
    started = time.monotonic()
    response = client.get('/v1/dream/runs')
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.headers['retry-after'] == '5'
    # A stalled gate never starts the state read, run stream, or count.
    assert streams == []
    assert elapsed < 5


def test_report_reads_each_edit_target_once_per_run(client, runtime, monkeypatch):
    """The documented bound: gate + state + run stream + count + one read per unique target per run."""
    monkeypatch.setenv('OMI_LIST_READ_BUDGET_SECONDS', '2')
    now = datetime.now(timezone.utc)
    seed_owner(
        runtime,
        dirty=3,
        runs=[
            ('newer-run', now, ['conversations/one', 'conversations/two']),
            ('older-run', now - timedelta(minutes=1), ['conversations/one']),
        ],
    )
    target_reads = []
    monkeypatch.setattr(
        dream_report.dream_reads,
        'read_record',
        lambda uid, ref, **kwargs: target_reads.append(ref) or {'structured': {'title': 'T'}},
    )
    before = list(runtime.reads)
    response = client.get('/v1/dream/runs?limit=10')

    assert response.status_code == 200
    assert 'x-omi-list-truncated' not in {key.lower() for key in response.headers}
    assert len(response.json()['runs']) == 2 and response.json()['queued_changes'] == 3
    assert Counter(target_reads) == Counter({'conversations/one': 2, 'conversations/two': 1})
    # One gate document and one state document; the run stream and the count
    # aggregation are index reads, and no run row or target is read twice.
    assert runtime.reads[len(before) :] == [('users', UID), ('dream_users', UID)]
