"""Owner-only API and independent transactional manual allowances."""

import asyncio
import json
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.dream_agent import Caps
from database import dream_store, review_store
from routers import dream_report as routes
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
        dream_report.dream_reads, 'read_record', lambda *args: {'structured': {'title': 'Synthetic report'}}
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
