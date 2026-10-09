"""Real dirty hook, encrypted storage, transport lanes and canary failure attribution offline."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.dream_agent import eligible
from database import dream_canary as storage, dream_store, conversations
from routers import dream_sweep
from tests.support.dream_firestore import DreamFirestore
from utils import dream_canary, dream_reads, dream_transport, dream_agent

UID = 'dream-canary-synthetic'


@pytest.fixture
def store(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', UID)
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(storage, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_reads.screen_activity, 'get_screen_activity', lambda *a, **k: [])

    async def post(url, **kwargs):
        body = kwargs['json']
        assert body['max_completion_tokens'] <= 256
        model = body['model']
        value = (
            {'clusters': [{'refs': ['conversations/' + storage.RECORD_ID], 'problem': 'spelling'}]}
            if model == dream_transport.TRIAGE_LANE
            else {}
        )
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'usage': {'prompt_tokens': 30, 'completion_tokens': 20},
                'choices': [{'message': {'content': json.dumps(value)}}],
            },
        )

    client = type('Client', (), {'post': AsyncMock(side_effect=post)})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    return db, client


def test_canary_full_loop_real_serialization_and_transport_shadow_in_on(store, caplog):
    db, client = store
    with caplog.at_level('INFO', logger='utils.dream_canary'):
        result = asyncio.run(dream_canary.check())
    assert result == {'status': 'pass', 'stage': 'report', 'error_type': 'none', 'consecutive_failures': 0}
    calls = [call.kwargs['json']['model'] for call in client.post.call_args_list]
    assert calls == [dream_transport.TRIAGE_LANE, dream_transport.MAIN_LANE]
    assert dream_store.dirty_count(UID) == 0
    doc = dream_store.own_runs(UID)[0][1]
    assert doc['mode'] == 'shadow' and doc['tokens'] == 100
    assert doc['records_read'] == 1 and doc['records_queued_after'] == 0
    assert 'review_encrypted_v1' in doc['source']
    assert db.rows[('dream_spend', doc['created_at'].date().isoformat())]['reserved_usd'] == pytest.approx(0.16)
    assert not eligible(UID, db.rows[('users', UID)])
    assert not dream_store.mark_dirty(UID, [('conversations', 'other')])
    assert UID not in caplog.text and 'Qorbi' not in caplog.text
    assert 'Dream canary status=pass stage=report error_type=none' in caplog.text


@pytest.mark.parametrize('stage', ['enqueue', 'admit', 'model', 'report'])
def test_canary_failures_identify_stage_and_reset_streak(store, monkeypatch, stage):
    db, client = store

    def broken(*a, **k):
        raise RuntimeError('private provider body')

    if stage == 'enqueue':
        monkeypatch.setattr(storage, 'write_record', broken)
    elif stage == 'admit':
        monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: None)
    elif stage == 'model':
        client.post.side_effect = httpx.ReadError('private provider body')
    else:
        monkeypatch.setattr(dream_store, 'own_run', lambda *a: None)
    first = asyncio.run(dream_canary.check())
    second = asyncio.run(dream_canary.check())
    assert first['status'] == second['status'] == 'fail'
    assert first['stage'] == second['stage'] == stage
    assert second['consecutive_failures'] == 2
    assert storage.record_result(True) == 0
    assert storage.record_result(False) == 1
    assert 'private' not in json.dumps(first)


def test_existing_owner_is_never_overwritten(store):
    db, client = store
    db.rows[('users', UID)] = {'name': 'existing'}
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'fail' and result['stage'] == 'enqueue'
    assert db.rows[('users', UID)] == {'name': 'existing'}
    assert not dream_store.own_runs(UID)
    client.post.assert_not_called()


def test_canary_uses_same_oidc_guard_as_sweep(store):
    app = FastAPI()
    app.include_router(dream_sweep.router)
    response = TestClient(app).post('/v2/dream-agent/canary')
    assert response.status_code == 403


def test_scheduler_prod_and_paused_dev_auth_match_sweep():
    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((root / 'backend/deploy/scheduler/jobs.yaml').read_text())
    prod = config['environments']['prod']['jobs']
    sweep = next(row for row in prod if row['name'] == 'dream-agent-sweep-hourly')
    canary = next(row for row in prod if row['name'] == 'dream-agent-canary-half-hourly')
    assert canary['schedule'] == '*/30 * * * *' and canary['state'] == 'ENABLED'
    assert canary['target']['oidc'] == sweep['target']['oidc'] and canary['retry'] == sweep['retry']
    assert canary['target']['uri'] == sweep['target']['uri'].replace('/sweep', '/canary')
    dev = next(row for row in config['environments']['dev']['jobs'] if row['name'] == canary['name'])
    assert dev['state'] == 'PAUSED'
