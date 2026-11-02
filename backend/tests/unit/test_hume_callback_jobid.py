"""#20284 — a Hume callback with a missing/empty job_id must be rejected 400.

Before the fix, from_dict() always built a model so a null job_id flowed into
process_user_expression_measurement_callback and crashed downstream.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import agents as agents_router


def _client(called):
    import routers.agents as m

    def fake_process(provider, job_id, callback):
        called.append((provider, job_id))

    import types

    class _TaskActionProvider:
        HUME = 'hume'

    m.process_user_expression_measurement_callback = fake_process
    m.task = types.SimpleNamespace(TaskActionProvider=_TaskActionProvider)
    app = FastAPI()
    app.include_router(agents_router.router)
    return TestClient(app)


def test_missing_job_id_returns_400():
    called = []
    client = _client(called)
    assert client.post('/v1/agents/hume/callback', json={'status': 'COMPLETED'}).status_code == 400
    assert called == []


def test_empty_job_id_returns_400():
    called = []
    client = _client(called)
    assert client.post('/v1/agents/hume/callback', json={'job_id': '', 'status': 'COMPLETED'}).status_code == 400
    assert called == []


def test_empty_body_returns_400():
    called = []
    client = _client(called)
    assert client.post('/tmp/v1/agents/hume/callback'.replace('/tmp', ''), json={}).status_code == 400
    assert called == []


def test_valid_job_id_processes():
    called = []
    client = _client(called)
    response = client.post('/v1/agents/hume/callback', json={'job_id': 'job-123', 'status': 'COMPLETED'})
    assert response.status_code == 200
    assert called == [('hume', 'job-123')]
