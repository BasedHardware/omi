"""Actual Dream coordinator, storage admission, verified journal apply and Undo."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from config.dream_agent import Caps
from config.dream_session import SessionLimits
from database import dream_store, dream_turns, review_store, review_changes
from models.agent_tools import VerificationBatch, Verification
from tests.unit.test_dream_cleanup_edits import store, records, UID
from tests.unit.test_dream_session import call, turn
from utils.agent_capabilities import tools as dream_tools
from utils import dream_agent, dream_seed, dream_capacity
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.llm.shaped_agent import Turn


@pytest.fixture
def runtime(store, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *args: set())
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_turns.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=('synthetic-slot', 'synthetic-token')))
    monkeypatch.setattr(dream_capacity, 'release', AsyncMock())
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records(store).get(ref))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: (
            {'targets': list(records(store)), 'vocabulary': []},
            EvidenceRecords(records(store)),
            [],
            SessionLimits(),
        ),
    )
    return store


def scripted(votes, *, on_plan=None):
    verified = 0

    async def model(uid, lane, mount, messages):
        nonlocal verified
        if lane == MAIN_LANE:
            if on_plan:
                on_plan()
            return turn(
                [
                    call(
                        'propose_edit',
                        {
                            'edit': {
                                'kind': 'dismiss_person',
                                'target': 'people/junk',
                                'evidence': ['conversations/one'],
                                'reason': 'Synthetic junk profile',
                                'value': 4,
                            }
                        },
                    ),
                    call(
                        'finish',
                        {'summary': 'Checked synthetic records', 'notes': 'Look for repeated junk profiles'},
                        2,
                    ),
                ],
                tokens=10,
            )
        assert lane == VERIFY_LANE
        import json

        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        assert 'UNTRUSTED SEED' not in messages[-1]['content']
        vote = votes[verified]
        verified += 1
        return Turn(
            tokens=20,
            prompt_tokens=15,
            cached_tokens=5,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=vote, reason='Synthetic independent evidence check')
                    for row in batch
                ]
            ),
        )

    return model


@pytest.mark.parametrize(
    'votes,status', [([True, True], 'applied'), ([True, False], 'suggested'), ([False, False], 'verifier_disagree')]
)
def test_two_verifiers_select_apply_review_or_drop_and_report_counts(runtime, votes, status):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted(votes)))
    assert report['status'] == 'complete', str(report)
    assert report['tokens'] == 50 and report['cached_tokens'] == 10
    assert report['verifier_calls'] == 2 and report['turns'] == 1
    assert report['outcomes'][0]['status'] == status
    assert runtime.rows[('dream_users', UID)]['lease'] is None
    day = next(key[3] for key in runtime.rows if key[:3] == ('dream_users', UID, 'spend'))
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] == pytest.approx(0.0005)
    assert sum(
        row['reserved_usd'] for key, row in runtime.rows.items() if key[0] == 'dream_global_spend'
    ) == pytest.approx(0.0005)
    assert runtime.rows[('dream_users', UID, 'spend', day)]['observed_usd'] == pytest.approx(0.0005)
    if status == 'applied':
        changes = [
            review_store.decode_doc(UID, value)['change']
            for key, value in runtime.rows.items()
            if key[2:3] == ('review_changes',)
        ]
        review_changes.set_undone(UID, changes[0]['change_id'], True)
        assert runtime.rows[('users', UID, 'people', 'junk')] == before
    else:
        assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_dry_run_runs_real_guards_and_verifiers_without_any_storage_writes(runtime):
    before = deepcopy(runtime.rows)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True]), dry_run=True))
    assert report['status'] == 'complete', report and report['outcomes'][0]['status'] == 'dry_run'
    assert runtime.rows == before and not runtime.transactions


def test_kill_switch_prevents_reads_model_calls_and_all_effects(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    monkeypatch.setattr(dream_seed, 'load', lambda *args: pytest.fail('Disabled seed read'))
    model = AsyncMock()
    assert asyncio.run(dream_agent.run_pass(UID, turn=model)) == {'status': 'not_admitted', 'reason': 'disabled'}
    model.assert_not_called()


def test_live_kill_after_planning_cannot_apply_staged_work(runtime, monkeypatch):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(
        dream_agent.run_pass(
            UID, turn=scripted([True, True], on_plan=lambda: monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false'))
        )
    )
    assert not report['outcomes']
    assert runtime.rows[('users', UID, 'people', 'junk')] == before
