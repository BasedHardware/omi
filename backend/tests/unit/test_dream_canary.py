"""Synthetic canary traverses seed, tools, two verifiers and encrypted dry effects."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.dream_session import SessionLimits
from database import dream_canary as storage, dream_store, conversations, review_store
from models.agent_tools import VerificationBatch, Verification
from tests.support.dream_firestore import DreamFirestore
from tests.unit.test_dream_session import call, turn
from utils.agent_capabilities import tools as dream_tools
from utils import dream_canary, dream_agent, dream_seed
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.llm.shaped_agent import Turn
from routers import dream_sweep

UID = 'dream-canary-synthetic'


@pytest.fixture
def canary(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', UID)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(storage, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *args: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *args: set())
    monkeypatch.setattr(dream_agent.dream_capacity, 'claim', AsyncMock(return_value=('synthetic', 'slot')))
    monkeypatch.setattr(dream_agent.dream_capacity, 'release', AsyncMock())
    ref = 'conversations/' + storage.RECORD_ID

    def load(uid, caps):
        raw = db.rows[('users', uid, 'conversations', storage.RECORD_ID)]
        row = conversations.prepare_conversation_for_read(deepcopy(raw), uid)
        dirty = [snapshot.to_dict() for snapshot in dream_store.dirty_refs(uid)]
        return {'targets': [ref], 'vocabulary': []}, EvidenceRecords({ref: row}), dirty, SessionLimits(edits=1)

    monkeypatch.setattr(dream_seed, 'load', load)
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, key, snapshot: load(uid, None)[1][key])
    lanes = []

    async def model(uid, lane, mount, messages, **kwargs):
        lanes.append(lane)
        if lane == MAIN_LANE:
            return turn(
                [
                    call(
                        'propose_edit',
                        {
                            'edit': {
                                'kind': 'spelling',
                                'target': ref,
                                'before': 'Qorby',
                                'after': 'Qorbi',
                                'reason': 'Synthetic explicitly spelled name',
                                'evidence': [ref],
                            }
                        },
                    ),
                    call('finish', {'summary': 'Synthetic check'}, 2),
                ]
            )
        import json

        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=10,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=True, reason='Explicit spelling in synthetic evidence')
                    for row in batch
                ]
            ),
        )

    monkeypatch.setattr(dream_agent.dream_harness_transport, 'model_turn', model)

    # Scripted turns still exercise the transport usage observer contract.
    async def observed(uid, lane, mount, messages, **kwargs):
        result = await model(uid, lane, mount, messages)
        await kwargs['on_usage'](result)
        return result

    monkeypatch.setattr(dream_agent.dream_harness_transport, 'model_turn', observed)
    return db, lanes


def test_canary_deterministic_tools_real_verifier_seam_journal_undo_and_report(canary):
    db, lanes = canary
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'pass', result
    assert lanes == [VERIFY_LANE, VERIFY_LANE]
    runs = dream_store.own_runs(UID)
    assert len(runs) == 1 and runs[0][1]['mode'] == 'shadow'
    assert set(runs[0][1]['source']) == {'review_encrypted_v1'}
    decoded = review_store.decode_doc(UID, runs[0][1])['source']
    assert decoded['outcomes'][0]['status'] == 'dry_run'
    assert decoded['verifier_valid_responses'] == 2 and decoded['tool_counts']['propose_edit'] == 1
    assert not any(path[2:3] in [('review_changes',), ('review_proposals',)] for path in db.rows)
    row = conversations.prepare_conversation_for_read(db.rows[('users', UID, 'conversations', storage.RECORD_ID)], UID)
    assert 'Qorby' in row['transcript_segments'][0]['text']
    overlay = review_store.decode_doc(UID, db.rows[('users', UID, 'transcript_corrections', storage.RECORD_ID)])
    assert overlay['source'][0]['undone'] is True
    assert any(path[2:3] == ('review_changes',) for tx in db.transactions for path, _ in tx.sets)


def test_canary_refuses_existing_unmarked_owner(canary):
    db, lanes = canary
    db.rows[('users', UID)] = {'name': 'existing synthetic owner'}
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'fail' and result['stage'] == 'enqueue'
    assert db.rows[('users', UID)] == {'name': 'existing synthetic owner'} and not lanes


def test_canary_repeats_without_model_target_selection_or_suppression_leak(canary):
    db, lanes = canary
    results = [asyncio.run(dream_canary.check()) for _ in range(3)]
    assert [result['status'] for result in results] == ['pass'] * 3
    assert lanes == [VERIFY_LANE] * 6
    assert len(dream_store.own_runs(UID)) == 3
    assert not any(path[2:3] in [('review_changes',), ('review_do_not_redo',)] for path in db.rows)


def test_verifier_disagreement_does_not_decide_pipeline_health(canary, monkeypatch):
    _, lanes = canary
    original = dream_agent.dream_harness_transport.model_turn

    async def disagree(uid, lane, mount, messages, **kwargs):
        result = await original(uid, lane, mount, messages, **kwargs)
        for decision in result.value.decisions:
            decision.agree = False
            decision.reason = 'Synthetic semantic disagreement; the wire is healthy'
        return result

    monkeypatch.setattr(dream_agent.dream_harness_transport, 'model_turn', disagree)
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'pass', result
    assert lanes == [VERIFY_LANE, VERIFY_LANE]


def test_failed_undo_does_not_poison_next_canary(canary, monkeypatch):
    db, _ = canary
    original = dream_canary.review_changes.set_undone
    monkeypatch.setattr(
        dream_canary.review_changes,
        'set_undone',
        lambda *args: (_ for _ in ()).throw(RuntimeError('Synthetic failure')),
    )
    assert asyncio.run(dream_canary.check())['status'] == 'fail'
    assert any(path[2:3] == ('review_changes',) for path in db.rows)
    monkeypatch.setattr(dream_canary.review_changes, 'set_undone', original)
    assert asyncio.run(dream_canary.check())['status'] == 'pass'
    assert not any(path[2:3] in [('review_changes',), ('review_do_not_redo',)] for path in db.rows)


def test_operator_env_kill_skips_without_counting_a_failure(canary, monkeypatch):
    db, lanes = canary
    db.rows[('dream_canary_health', 'current')] = {'canary_failures': 2}
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    called = []
    monkeypatch.setattr(dream_canary, 'seed', lambda uid: called.append(uid))
    result = asyncio.run(dream_canary.check())
    assert result == {
        'status': 'skipped',
        'stage': 'enqueue',
        'error_type': 'disabled',
        'consecutive_failures': 0,
    }
    assert called == [] and not lanes
    assert db.rows[('dream_canary_health', 'current')]['canary_failures'] == 0


def test_dynamic_kill_skips_without_counting_a_failure(canary, monkeypatch):
    db, lanes = canary
    db.rows[('dream_canary_health', 'current')] = {'canary_failures': 2}
    monkeypatch.setattr('config.dream_control.allowed', lambda: False)
    called = []
    monkeypatch.setattr(dream_canary, 'seed', lambda uid: called.append(uid))
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'skipped' and result['error_type'] == 'disabled'
    assert result['consecutive_failures'] == 0 and called == [] and not lanes
    assert db.rows[('dream_canary_health', 'current')]['canary_failures'] == 0


def test_missing_canary_uid_is_a_real_failure(canary, monkeypatch):
    db, lanes = canary
    monkeypatch.delenv('DREAM_AGENT_CANARY_UID')
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'fail' and result['stage'] == 'enqueue' and not lanes
    assert result['consecutive_failures'] == 1
    assert db.rows[('dream_canary_health', 'current')]['canary_failures'] == 1


def test_canary_alert_counts_failures_and_ignores_skips():
    metric = json.loads(
        (Path(__file__).resolve().parents[2] / 'deploy/monitoring/dream-canary-failures.metric.json').read_text()
    )
    pattern = r'Dream canary status=fail .*consecutive_failures=([2-9]|[1-9][0-9]+)( |$)'
    skipped = 'Dream canary status=skipped stage=enqueue error_type=disabled consecutive_failures=0'
    failed = 'Dream canary status=fail stage=enqueue error_type=CanaryFailure consecutive_failures=2'
    assert re.search(pattern, skipped) is None
    assert re.search(pattern, failed)
    assert pattern in metric['filter']
    assert 'status=skipped' not in metric['filter']


def test_canary_uses_scheduler_oidc_and_long_declared_deadline():
    app = FastAPI()
    app.include_router(dream_sweep.router)
    assert TestClient(app).post('/v2/dream-agent/canary').status_code == 403
    config = yaml.safe_load((Path(__file__).resolve().parents[3] / 'backend/deploy/scheduler/jobs.yaml').read_text())
    prod = config['environments']['prod']['jobs']
    canary = next(row for row in prod if row['name'] == 'dream-agent-canary-half-hourly')
    sweep = next(row for row in prod if row['name'] == 'dream-agent-sweep-hourly')
    assert canary['target']['oidc'] == sweep['target']['oidc']
    assert int(canary['attempt_deadline'][:-1]) > dream_canary.DEADLINE_SECONDS


def test_empty_verifier_decisions_are_a_healthy_non_apply(canary, monkeypatch):
    from models.agent_tools import VerificationBatch

    original = dream_agent.dream_harness_transport.model_turn

    async def empty(uid, lane, mount, messages, **kwargs):
        result = await original(uid, lane, mount, messages, **kwargs)
        result.value = VerificationBatch(decisions=[])
        return result

    monkeypatch.setattr(dream_agent.dream_harness_transport, 'model_turn', empty)
    assert asyncio.run(dream_canary.check())['status'] == 'pass'


def test_completed_malformed_verifier_payload_is_a_healthy_non_apply(canary, monkeypatch):
    original = dream_agent.dream_harness_transport.model_turn

    async def malformed(uid, lane, mount, messages, **kwargs):
        await original(uid, lane, mount, messages, **kwargs)
        kwargs['usage_sink']['transport_complete'] = True
        raise ValueError('Synthetic malformed decision payload')

    monkeypatch.setattr(dream_agent.dream_harness_transport, 'model_turn', malformed)
    assert asyncio.run(dream_canary.check())['status'] == 'pass'
