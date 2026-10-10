"""Owner-only API and independent transactional manual allowances."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.dream_agent import Caps
from database import dream_store, review_store
from models.dream_agent import Plan, Edit, Term, Feedback
from routers import dream_report as routes
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_reads, dream_report, dream_transport
from utils.llm.shaped_agent import Turn
from scripts.export_openapi import build_openapi
from scripts.generate_dart_models import build_output

UID = 'synthetic-report-owner'


def test_checked_in_dream_schema_and_mobile_dtos_match_real_routes():
    root = Path(__file__).resolve().parents[3]
    app = FastAPI()
    app.include_router(routes.router)
    spec = json.loads((root / 'backend/docs/api/dream-openapi.json').read_text())
    assert spec == build_openapi(app, 'dream')
    assert (root / 'app/lib/backend/schema/gen/dream_wire.g.dart').read_text() == build_output(spec, 'dream')
    assert 'GeneratedDreamRunRequest({' not in build_output(spec, 'dream')


@pytest.fixture
def store(monkeypatch):
    db = DreamFirestore()
    db.rows[('users', UID)] = {}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_SELF_REPORT_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'false')
    monkeypatch.setenv('DREAM_AGENT_MANUAL_RUNS_PER_DAY', '3')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_report, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_agent.review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(dream_reads.screen_activity, 'get_screen_activity', lambda *a, **k: [])
    monkeypatch.setattr(dream_reads, 'read_record', lambda uid, ref: {'structured': {'title': 'Synthetic sync'}})
    return db


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('gate', ['off', 'stranger', 'dream_off'])
def test_disabled_and_outside_cohort_are_exact_404(client, monkeypatch, gate, method):
    if gate == 'off':
        monkeypatch.setenv('DREAM_SELF_REPORT_MODE', 'off')
    elif gate == 'dream_off':
        monkeypatch.setenv('DREAM_AGENT_MODE', 'off')
    else:
        monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', 'other')
    response = getattr(client, method)('/v1/dream/runs', **({'json': {}} if method == 'post' else {}))
    assert response.status_code == 404
    assert response.json() == {'detail': 'dream_report_disabled'}


def test_manual_lease_cap_and_idle_are_separate_from_schedule(store, client):
    today = datetime.now(timezone.utc).date().isoformat()
    store.rows[('dream_users', UID)] = {'day': today, 'passes': 2, 'manual_runs': 0, 'score': 0}
    assert client.post('/v1/dream/runs', json={}).json()['status'] == 'idle'
    assert store.rows[('dream_users', UID)]['manual_runs'] == 0
    dream_store.mark_dirty(UID, [('conversations', 'c1')])
    lease = dream_store.acquire(UID, Caps(), trigger='manual')
    assert lease['trigger'] == 'manual'
    assert store.rows[('dream_users', UID)]['passes'] == 2
    assert store.rows[('dream_users', UID)]['manual_runs'] == 1
    assert client.post('/v1/dream/runs', json={}).json() == {'detail': 'dream_run_in_progress'}
    assert client.post('/v1/dream/runs', json={}).status_code == 409
    dream_store.finish(UID, lease, {'tokens': 1}, success=False)
    store.rows[('dream_users', UID)]['manual_runs'] = 3
    assert client.post('/v1/dream/runs', json={}).status_code == 429
    assert client.post('/v1/dream/runs', json={}).json() == {'detail': 'dream_manual_limit'}
    assert dream_store.acquire(UID, Caps(passes=3)) is not None


def test_manual_respects_global_ceiling(store, client):
    dream_store.mark_dirty(UID, [('conversations', 'c1')])
    store.rows[('dream_spend', datetime.now(timezone.utc).date().isoformat())] = {'reserved_usd': 20}
    assert client.post('/v1/dream/runs', json={}).status_code == 503
    assert 'lease' not in store.rows[('dream_users', UID)]


def test_manual_idle_refunds_correct_allowance(store, client, monkeypatch):
    dream_store.mark_dirty(UID, [('conversations', 'deleted')])
    monkeypatch.setattr(dream_reads, 'read_record', lambda *a: None)
    response = client.post('/v1/dream/runs', json={})
    assert response.status_code == 200 and response.json()['status'] == 'idle'
    state = store.rows[('dream_users', UID)]
    assert state['manual_runs'] == state['passes'] == 0
    assert store.rows[('dream_spend', state['day'])]['reserved_usd'] == 0
    assert client.get('/v1/dream/runs').json()['runs'] == []


def test_projection_strips_evidence_reproductions_and_extra_diagnostics(store, client):
    source = {
        'status': 'complete',
        'proposed': {
            'questions': [{'kind': 'same_person', 'title': 'Are these the same robot?', 'item_id': 'private-id'}],
            'slow_tasks': [{'description': 'Send the synthetic proposal', 'evidence': ['private-ref']}],
            'vocabulary': [{'kind': 'jargon', 'spelling': 'Qorbi', 'aliases': ['Qorby'], 'evidence': ['private-ref']}],
            'feedback': [
                Feedback(
                    component='notes',
                    failure_class='spelling',
                    severity='warning',
                    count=3,
                    latency_ms=2,
                    error_rate=0.1,
                    reproduction='private-reproduction',
                ).model_dump()
            ],
        },
        'outcomes': [{'tool': 'feedback', 'status': 'privacy_rejected'}],
        'usage_unknown': True,
    }
    store.rows[('users', UID, 'dream_runs', 'report')] = {
        **review_store.encode_doc(UID, {'source': source}),
        'created_at': datetime.now(timezone.utc),
    }
    response = client.get('/v1/dream/runs')
    run = response.json()['runs'][0]
    assert run['questions'] == [{'kind': 'same_person', 'text': 'Are these the same robot?'}]
    assert run['privacy_rejected'] == 1
    assert run['feedback'] == [{'component': 'notes', 'failure_class': 'spelling', 'severity': 'warning', 'count': 3}]
    assert (
        'private-' not in response.text and 'usage_unknown' not in response.text and 'latency_ms' not in response.text
    )


def test_run_now_and_list_decrypt_same_contract_without_refs(store, client, monkeypatch):
    dream_store.mark_dirty(UID, [('conversations', 'c1')])
    plan = Plan(
        edits=[
            Edit(
                kind='spelling',
                target='conversations/c1',
                before='Qorby',
                after='Qorbi',
                reason='Consistent spelling',
                evidence=['conversations/c1'],
            )
        ],
        vocabulary=[Term(kind='jargon', spelling='Qorbi', aliases=['Qorby'], evidence=['conversations/c1'])],
    )

    async def turn(uid, lane, mount, messages, **kwargs):
        from models.dream_agent import Triage, Cluster

        sink = kwargs['usage_sink']
        sink['tokens'] += 10
        sink['usage_unknown'] = False
        return Turn(
            value=(
                Triage(clusters=[Cluster(refs=['conversations/c1'], problem='spelling')])
                if lane == dream_transport.TRIAGE_LANE
                else plan
            ),
            tokens=10,
        )

    monkeypatch.setattr(dream_transport, 'model_turn', turn)
    response = client.post('/v1/dream/runs', json={})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['status'] == 'complete' and run['trigger'] == 'manual'
    assert run['records_read'] == 1 and run['records_queued_after'] == 0 and run['tokens'] == 20
    assert run['edits'][0]['target_label'] == 'Conversation · Synthetic sync'
    assert run['edits'][0]['outcome'] == 'shadow' and run['edits'][0]['evidence_count'] == 1
    assert 'conversations/c1' not in response.text
    doc = store.rows[('users', UID, 'dream_runs', run['run_id'])]
    assert 'review_encrypted_v1' in doc['source']
    assert {key: doc[key] for key in ('records_read', 'records_queued_after', 'tokens', 'cost_usd')} == {
        key: run[key] for key in ('records_read', 'records_queued_after', 'tokens', 'cost_usd')
    }
    stranger = ('users', 'stranger', 'dream_runs', 'private')
    store.rows[stranger] = {'created_at': datetime.now(timezone.utc), 'source': 'private'}
    listed = client.get('/v1/dream/runs').json()
    assert listed['runs'] == [run]
    assert listed['manual_runs_today'] == 1 and listed['passes_today'] == 0
    assert listed['queued_changes'] == 0
    monkeypatch.setattr(dream_reads, 'read_record', lambda *a: None)
    assert client.get('/v1/dream/runs').json()['runs'][0]['edits'][0]['target_label'] == 'Deleted item'


def test_newest_first_bounded_and_legacy_trigger(store, client):
    for i in range(25):
        store.rows[('users', UID, 'dream_runs', str(i))] = {
            **review_store.encode_doc(UID, {'source': {'status': 'complete'}}),
            'created_at': datetime(2026, 10, 9, 0, i, tzinfo=timezone.utc),
        }
    runs = client.get('/v1/dream/runs?limit=20').json()['runs']
    assert len(runs) == 20 and runs[0]['run_id'] == '24' and runs[-1]['run_id'] == '5'
    assert all(row['trigger'] == 'schedule' for row in runs)


def test_enriched_entity_targets_resolve_owner_labels(store, client, monkeypatch):
    seen = []

    def resolve(uid, key):
        seen.append((uid, key))
        return {'name': 'Synthetic robot'}

    monkeypatch.setattr(dream_reads, 'resolve_entity', resolve)
    source = {
        'status': 'complete',
        'proposed': {
            'edits': [
                Edit(
                    kind='entity_summary',
                    target='entity/person:opaque-key',
                    after='Summary',
                    reason='Supported',
                    evidence=['entity/person:opaque-key'],
                ).model_dump(),
            ]
        },
        'outcomes': [{'key': 'edit-key', 'status': 'shadow'}],
    }
    store.rows[('users', UID, 'dream_runs', 'entity-run')] = {
        **review_store.encode_doc(UID, {'source': source}),
        'created_at': datetime.now(timezone.utc),
    }
    response = client.get('/v1/dream/runs')
    assert response.json()['runs'][0]['edits'][0]['target_label'] == 'Entity · Synthetic robot'
    assert seen == [(UID, 'person:opaque-key')]
    assert 'opaque-key' not in response.text


def test_deadline_includes_admission_and_retains_ambiguous_state(client, store, monkeypatch):
    monkeypatch.setattr(routes, 'MANUAL_DEADLINE_SECONDS', 0.01)

    async def stall(*a, **k):
        await asyncio.Event().wait()

    monkeypatch.setattr(dream_agent, 'run_pass', stall)
    response = client.post('/v1/dream/runs', json={})
    assert response.status_code == 200 and response.json()['status'] == 'deadline'


def test_manual_refund_after_midnight_does_not_decrement_new_day(store):
    dream_store.mark_dirty(UID, [('conversations', 'c1')])
    lease = dream_store.acquire(UID, Caps(), trigger='manual')
    store.rows[('dream_users', UID)].update(day='2099-01-01', manual_runs=2, passes=1)
    dream_store.finish(UID, lease, {'tokens': 0}, success=False, refund=True)
    assert store.rows[('dream_users', UID)]['manual_runs'] == 2


def test_untitled_summary_target_is_visible_in_report():
    assert (
        dream_report.target_label('conversations/synthetic', {'structured': {'title': ''}}) == 'Untitled conversation'
    )
    assert dream_report.target_label('conversations/synthetic', None) == 'Deleted item'
