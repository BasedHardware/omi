import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import desktop_prompts as router_module
from routers.desktop_prompts import prompt_matches_audience, spec_from_doc


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: 'test_uid_123'
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_get_desktop_prompts_route_success(client, monkeypatch):
    docs = [
        FakeSnapshot('p2', {'type': 'stars', 'question': 'Rate 1-5', 'active': True}),
        FakeSnapshot('p1', {'type': 'nps', 'question': 'Recommend us?', 'active': True}),
    ]
    monkeypatch.setattr(router_module, 'list_active_desktop_prompt_snapshots', lambda: docs)

    resp = client.get('/v2/desktop/prompts')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data['prompts']) == 2
    # Verify sorted by ID
    assert data['prompts'][0]['id'] == 'p1'
    assert data['prompts'][1]['id'] == 'p2'


def test_get_desktop_prompts_negative_build_returns_400(client):
    resp = client.get('/v2/desktop/prompts?build=-1')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Build must be non-negative'


def test_get_desktop_prompts_invalid_channel_returns_400(client):
    too_long = 'c' * 100
    resp = client.get(f'/v2/desktop/prompts?channel={too_long}')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Invalid channel'


def test_get_desktop_prompts_db_exception_returns_500_sanitized(client, monkeypatch):
    def fake_list():
        raise RuntimeError("Firestore connection failure: secret_host_db_internal:8080")

    monkeypatch.setattr(router_module, 'list_active_desktop_prompt_snapshots', fake_list)
    resp = client.get('/v2/desktop/prompts')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to retrieve desktop prompts'
    assert 'secret_host' not in resp.text


def test_poisoned_document_does_not_crash_endpoint(client, monkeypatch):
    docs = [
        FakeSnapshot('valid1', {'type': 'stars', 'question': 'Valid prompt', 'active': True}),
        # Poison 1: string min_build that previously caused TypeError in build < min_build
        FakeSnapshot('poison1', {'type': 'stars', 'question': 'String build', 'audience': {'min_build': '12500'}}),
        # Poison 2: malformed rollout_pct string that previously caused ValueError
        FakeSnapshot(
            'poison2', {'type': 'banner', 'question': 'Broken rollout', 'audience': {'rollout_pct': 'invalid_string'}}
        ),
        # Poison 3: non-iterable options
        FakeSnapshot('poison3', {'type': 'choice', 'question': 'Choice with int options', 'options': 12345}),
        # Poison 4: completely raising snapshot
        FakeSnapshot('poison4', {'type': 'stars', 'question': None}),
        FakeSnapshot('valid2', {'type': 'nps', 'question': 'Second valid prompt', 'active': True}),
    ]
    monkeypatch.setattr(router_module, 'list_active_desktop_prompt_snapshots', lambda: docs)

    resp = client.get('/v2/desktop/prompts?build=13000')
    assert resp.status_code == 200
    data = resp.json()
    prompt_ids = [p['id'] for p in data['prompts']]
    # Ensure valid prompts are successfully delivered
    assert 'valid1' in prompt_ids
    assert 'valid2' in prompt_ids
    # poison4 (missing question) is cleanly skipped
    assert 'poison4' not in prompt_ids


def test_prompt_matches_audience_handles_malformed_fields():
    # String min_build should parse cleanly and compare correctly
    doc_str_build = {'id': 'p', 'audience': {'min_build': '12000'}}
    assert prompt_matches_audience(doc_str_build, 'u', 'stable', 12500)
    assert not prompt_matches_audience(doc_str_build, 'u', 'stable', 11000)

    # Garbage min_build falls back safely to 0
    doc_bad_build = {'id': 'p', 'audience': {'min_build': 'garbage'}}
    assert prompt_matches_audience(doc_bad_build, 'u', 'stable', 100)

    # String rollout_pct parses cleanly
    doc_str_rollout = {'id': 'p', 'audience': {'rollout_pct': '100'}}
    assert prompt_matches_audience(doc_str_rollout, 'u', 'stable', 0)

    # Garbage rollout_pct falls back safely to 100
    doc_bad_rollout = {'id': 'p', 'audience': {'rollout_pct': 'not_a_number'}}
    assert prompt_matches_audience(doc_bad_rollout, 'u', 'stable', 0)


def test_spec_from_doc_handles_malformed_structures():
    # Options as integer or None should not raise TypeError
    doc1 = {'id': 'p1', 'type': 'stars', 'question': 'Q1', 'options': 999}
    spec1 = spec_from_doc(doc1)
    assert spec1 is not None
    assert spec1.options == []

    # Non-dict trigger and cta
    doc2 = {'id': 'p2', 'type': 'stars', 'question': 'Q2', 'trigger': 'not_dict', 'cta': 'not_dict'}
    spec2 = spec_from_doc(doc2)
    assert spec2 is not None
    assert spec2.trigger_kind == 'app_launch'
    assert spec2.trigger_count == 0
    assert spec2.cta_label is None
