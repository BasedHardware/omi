"""Exercise Scheduler admission and the real bounded shadow worker offline."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.dream_agent import Caps
from database import dream_feedback, dream_store, dream_dirty
from models.dream_agent import Feedback, Plan, Edit, Term, FrameQuestion, SlowTask
from models.review import ReviewItem, SpellingItem
from routers import dream_sweep
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import cloud_tasks, dream_agent, dream_tools

UID = 'synthetic-owner'
AUDIENCE = 'https://synthetic-sync.example/v2/sync-jobs/run'
INVOKER = 'synthetic-scheduler@example.iam.gserviceaccount.com'
ROOT = Path(__file__).resolve().parents[3]


def load_yaml(path):
    return yaml.load(path.read_text(), Loader=yaml.CSafeLoader)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', AUDIENCE)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', INVOKER)
    monkeypatch.setattr(cloud_tasks, '_get_auth_request', lambda: object())
    app = FastAPI()
    app.include_router(dream_sweep.router)
    return TestClient(app)


@pytest.mark.parametrize('token', [None, 'wrong-audience', 'wrong-identity', 'unverified'])
def test_oidc_rejection_never_reaches_drain(client, monkeypatch, token):
    def verify(value, request, *, audience):
        assert audience == AUDIENCE
        if value == 'wrong-audience':
            raise ValueError('invalid audience')
        return {'email': INVOKER if value != 'wrong-identity' else 'other', 'email_verified': value != 'unverified'}

    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', verify)
    drain = AsyncMock()
    monkeypatch.setattr(dream_agent, 'drain', drain)
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
    assert client.post('/v2/dream-agent/sweep', headers=headers).status_code == 403
    drain.assert_not_called()


def test_authenticated_off_is_cheap_noop(client, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_MODE', 'off')
    monkeypatch.setattr(
        cloud_tasks.id_token,
        'verify_oauth2_token',
        lambda *a, **k: {
            'email': INVOKER,
            'email_verified': True,
        },
    )
    monkeypatch.setattr(dream_store, 'candidates', lambda **k: pytest.fail('off read Firestore'))
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: pytest.fail('off attempted admission'))
    response = client.post('/v2/dream-agent/sweep', headers={'Authorization': 'Bearer valid'})
    assert response.status_code == 200
    assert response.json() == {'complete': 0, 'failed': 0, 'not_admitted': 0, 'deadline': 0}


def test_route_returns_counts_only(client, monkeypatch):
    monkeypatch.setattr(
        cloud_tasks.id_token,
        'verify_oauth2_token',
        lambda *a, **k: {
            'email': INVOKER,
            'email_verified': True,
        },
    )
    monkeypatch.setattr(
        dream_agent,
        'drain',
        AsyncMock(
            return_value=[
                {'status': 'complete', 'proposed': {'private': 'synthetic private content'}, 'run_id': UID},
                {'status': 'failed', 'error_type': 'synthetic'},
                {'status': 'not_admitted'},
                {'status': 'deadline'},
            ]
        ),
    )
    response = client.post('/v2/dream-agent/sweep', headers={'Authorization': 'Bearer valid'})
    assert response.json() == {'complete': 1, 'failed': 1, 'not_admitted': 1, 'deadline': 1}
    assert UID not in response.text and 'private' not in response.text


@pytest.fixture
def store(monkeypatch):
    db = StrictFirestore()
    db.rows[('users', UID)] = {'name': 'Synthetic'}
    db.rows[('dream_users', UID)] = {'sequence': 1, 'watermark': 0, 'score': 1}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'false')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    return db


def test_stranger_not_admitted_or_reserving_spend(store):
    store.rows[('dream_users', 'stranger')] = {'sequence': 1, 'score': 1}
    store.rows[('users', 'stranger')] = {'dream_release_channel': 'testflight', 'dream_app_build': 9999}
    before = deepcopy(store.rows)
    assert asyncio.run(dream_agent.run_pass('stranger')) == {'status': 'not_admitted'}
    assert store.rows == before


def test_unset_salt_shadow_persists_complete_report_without_user_effects(store, monkeypatch):
    monkeypatch.delenv('DREAM_AGENT_FEEDBACK_SALT', raising=False)
    records = {'conversations/c1': {'id': 'c1', 'content': 'synthetic source words'}}
    feedback = Feedback(
        component='notes',
        failure_class='spelling',
        severity='warning',
        count=1,
        latency_ms=2,
        error_rate=0.1,
        reproduction='Invented robot examples demonstrate a failure.',
    )
    plan = Plan(
        edits=[
            Edit(
                kind='spelling',
                target='conversations/c1',
                before='typo',
                after='word',
                reason='Spelling',
                evidence=['conversations/c1'],
            )
        ],
        vocabulary=[Term(kind='jargon', spelling='Widget', evidence=['conversations/c1'])],
        slow_tasks=[SlowTask(description='Follow up later', evidence=['conversations/c1'])],
        questions=[
            ReviewItem(
                item_id='synthetic-question',
                kind='spelling',
                title='Which spelling?',
                created_at=datetime.now(timezone.utc),
                spelling=SpellingItem(term_id='synthetic-term', options=['one', 'two'], allow_custom=True),
            )
        ],
        frames=[FrameQuestion(screen_ref='screen/1', question='What image?')],
        feedback=[feedback],
    )
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (records, 1))
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(plan, 100)))

    def forbidden(*a, **k):
        pytest.fail('shadow wrote user data or developer feedback')

    for name in ('apply_edit', 'ask', 'propose_task', 'request_frame'):
        monkeypatch.setattr(dream_tools, name, forbidden)
    monkeypatch.setattr(dream_store, 'save_vocabulary', forbidden)
    monkeypatch.setattr(dream_feedback, 'store', forbidden)
    result = asyncio.run(dream_agent.run_pass(UID))
    assert result['status'] == 'complete'
    assert result['proposed']['feedback'] == [feedback.model_dump()]
    persisted = store.rows[('users', UID, 'dream_runs', result['run_id'])]
    decoded = dream_agent.review_store.decode_doc(UID, persisted)
    assert decoded['source']['status'] == 'complete'
    assert decoded['source']['proposed']['feedback'] == [feedback.model_dump()]
    assert store.rows[('users', UID)] == {'name': 'Synthetic'}
    assert set(store.rows) == {
        ('users', UID),
        ('dream_users', UID),
        ('dream_spend', datetime.now(timezone.utc).date().isoformat()),
        ('users', UID, 'dream_runs', result['run_id']),
    }


@pytest.mark.parametrize('stalled_stage', ['query', 'plan', 'finish'])
def test_wall_clock_bound_stops_drain_and_retains_ambiguous_lease(store, monkeypatch, stalled_stage):
    monkeypatch.setattr(dream_agent, 'DRAIN_TIMEOUT_SECONDS', 0.05)
    entered = asyncio.Event()
    pending = asyncio.Event()

    async def stall(*a, **k):
        entered.set()
        await pending.wait()

    real_blocking = dream_agent.run_blocking

    async def blocking(executor, fn, *a, **k):
        if stalled_stage == 'query' and fn is dream_store.candidates:
            return await stall()
        if stalled_stage == 'finish' and fn is dream_store.finish:
            return await stall()
        return await real_blocking(executor, fn, *a, **k)

    monkeypatch.setattr(dream_agent, 'run_blocking', blocking)
    monkeypatch.setattr(dream_store, 'candidates', lambda **k: [UID, 'never-started'])
    monkeypatch.setattr(
        dream_agent, 'plan_pass', stall if stalled_stage == 'plan' else AsyncMock(return_value=(Plan(), 0))
    )
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: ({}, 1))
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)

    async def exercise():
        start = asyncio.get_running_loop().time()
        result = await dream_agent.drain()
        assert asyncio.get_running_loop().time() - start < 0.5
        return result

    assert asyncio.run(exercise()) == [{'status': 'deadline'}]
    assert entered.is_set()
    if stalled_stage != 'query':
        assert store.rows[('dream_users', UID)]['lease']
        assert store.rows[('dream_users', UID)]['watermark'] == 0
        assert store.rows[('dream_users', UID)]['passes'] == 1


@pytest.mark.parametrize('collection', ['conversations', 'memories', 'memory_items', 'action_items'])
def test_shadow_write_hooks_dirty_queue(collection, store):
    writer = dream_dirty.after_write(collection)(lambda uid, data: data['id'])
    writer(UID, {'id': 'synthetic-record'})
    assert store.rows[('dream_users', UID)]['score'] == 2
    assert store.rows[('dream_users', UID, 'events', '2')]['refs'] == [[collection, 'synthetic-record']]


def test_prod_scheduler_and_writer_env_contract():
    scheduler = load_yaml(ROOT / 'backend/deploy/scheduler/jobs.yaml')
    jobs = scheduler['environments']['prod']['jobs']
    dream = next(job for job in jobs if job['name'] == 'dream-agent-sweep-hourly')
    sequencer = next(job for job in jobs if job['name'] == 'sync-backfill-uid-sequencer')
    assert dream['schedule'] == '0 * * * *' and dream['state'] == 'ENABLED'
    assert dream['target']['method'] == 'POST'
    assert dream['target']['uri'] == sequencer['target']['uri'].replace(
        '/v2/sync-backfill-sequencer/sweep', '/v2/dream-agent/sweep'
    )
    assert dream['target']['oidc'] == sequencer['target']['oidc']
    assert dream['retry'] == sequencer['retry']
    assert dream['attempt_deadline'] == '180s'
    assert dream_agent.DRAIN_TIMEOUT_SECONDS < 150 < int(dream['attempt_deadline'][:-1])
    assert not any(
        job['name'] == dream['name'] and job['state'] != 'PAUSED' for job in scheduler['environments']['dev']['jobs']
    )
    manifest = load_yaml(ROOT / 'backend/deploy/runtime_env.yaml')
    allowlist = '9OqYLlKJv4hmeYpIhwJcHBR975i2,vi7SA9ckQCe4ccobWNxlbdcNdC23'
    prod = manifest['environments']['prod']
    writers = [prod['gke']['backend-listen'], *prod['cloud_run']['services'].values()]
    for service in writers:
        assert service['env']['DREAM_AGENT_MODE']['value'] == 'shadow'
        assert service['env']['DREAM_AGENT_UID_ALLOWLIST']['value'] == allowlist
        assert 'DREAM_AGENT_TESTFLIGHT_ENABLED' not in service['env']
        assert not any(
            key.startswith('DREAM_AGENT_') and key not in {'DREAM_AGENT_MODE', 'DREAM_AGENT_UID_ALLOWLIST'}
            for key in service['env']
        )
    chart = load_yaml(ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml')
    env = {entry['name']: entry.get('value') for entry in chart['env']}
    assert env['DREAM_AGENT_MODE'] == 'shadow'
    assert env['DREAM_AGENT_UID_ALLOWLIST'] == allowlist
    dev = manifest['environments']['dev']
    for service in [dev['gke']['backend-listen'], *dev['cloud_run']['services'].values()]:
        assert service['env'].get('DREAM_AGENT_MODE', {}).get('value', 'off') == 'off'
