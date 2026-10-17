"""Actual Dream coordinator, storage admission, verified journal apply and Undo."""

import asyncio
import json
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
    # Scripted turns report no priced receipt, so the conservative 3.8 hold stays.
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] > 0
    assert not any(key[0] == 'dream_global_spend' for key in runtime.rows)
    assert runtime.rows[('dream_users', UID, 'spend', day)].get('observed_usd', 0) == pytest.approx(0)
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


def _proposals(runtime):
    return [
        review_store.decode_doc(UID, value)
        for key, value in runtime.rows.items()
        if key[:3] == ('users', UID, 'review_proposals')
    ]


def _plan(*, value=4):
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
                        'value': value,
                    }
                },
            ),
            call('finish', {'summary': 'Checked synthetic records', 'notes': 'Look for repeated junk profiles'}, 2),
        ],
        tokens=10,
    )


def _verdict(messages, agree):
    batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
    return Turn(
        tokens=20,
        value=VerificationBatch(
            decisions=[
                Verification(id=row['id'], agree=agree, reason='Synthetic independent evidence check') for row in batch
            ]
        ),
    )


def test_live_kill_after_planning_cannot_apply_staged_work(runtime, monkeypatch):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(
        dream_agent.run_pass(
            UID, turn=scripted([True, True], on_plan=lambda: monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false'))
        )
    )
    assert not report['outcomes']
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_default_unverified_is_recorded_and_not_offered(runtime):
    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            return _plan()
        raise RuntimeError('synthetic verifier failure')

    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert report['outcomes'][0]['status'] == 'verifier_unverified'
    assert _proposals(runtime) == []
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_non_default_unverified_is_offered_with_a_kind_title(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps({'dismiss_person': [{'strategy': 'cheap_model'}]}))
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        assert lane == MAIN_LANE
        return _plan()

    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert report['outcomes'][0]['status'] == 'suggested'
    assert lanes == [MAIN_LANE]
    proposals = _proposals(runtime)
    assert len(proposals) == 1
    item = proposals[0]['item']
    assert item['title'] == 'Dismiss person'
    assert item['agent_proposal']['edit']['reason'] == 'Synthetic junk profile'
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_non_default_unverified_below_the_offer_threshold_stays_recorded(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps({'dismiss_person': [{'strategy': 'cheap_model'}]}))

    async def model(uid, lane, mount, messages):
        return _plan(value=2)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'verifier_unverified'
    assert _proposals(runtime) == []


def test_cheap_turn_uses_the_named_lane_and_disagree_is_not_offered(runtime, monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'dismiss_person': [{'strategy': 'cheap_model', 'lane': 'synthetic-cheap'}]}),
    )
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        if lane == MAIN_LANE:
            return _plan()
        assert lane == 'synthetic-cheap'
        return _verdict(messages, False)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert lanes == [MAIN_LANE, 'synthetic-cheap']
    assert report['outcomes'][0]['status'] == 'verifier_disagree'
    assert _proposals(runtime) == []


def test_verify_lane_is_not_used_as_the_cheap_turn(runtime, monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'dismiss_person': [{'strategy': 'cheap_model', 'lane': VERIFY_LANE}]}),
    )
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        assert lane == MAIN_LANE
        return _plan()

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'suggested'
    assert lanes == [MAIN_LANE]
    assert _proposals(runtime)[0]['item']['title'] == 'Dismiss person'


def test_price_weighted_cache_usage_allows_more_main_turns_than_raw_tokens(runtime, monkeypatch):
    limits = SessionLimits(bucket='light', turns=8, tools=8, read_bytes=64000, read_call_bytes=64000, tokens=10000)
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )
    main_calls = []

    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        main_calls.append(messages)
        if len(main_calls) <= 5:
            tool_call = call('read', {'refs': ['conversations/one']}, index=len(main_calls))
            return Turn(
                tokens=4000,
                prompt_tokens=4000,
                completion_tokens=0,
                cached_tokens=3500,
                tool_calls=(tool_call,),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
            )
        return turn([call('finish', {'summary': 'Checked cached records', 'notes': ''}, index=99)], tokens=4000)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert report['turns'] == 6
    assert report['tokens'] == 24000 and report['cached_tokens'] == 17500
    assert report['price_weighted_tokens'] == 8250 < limits.tokens
    assert report['accounted_tokens'] == report['tokens']


def test_unreported_cache_is_full_price_in_real_run_pass(runtime, monkeypatch):
    limits = SessionLimits(bucket='light', turns=3, tools=2, read_bytes=64000, read_call_bytes=64000, tokens=10000)
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )
    main_calls = 0

    async def model(uid, lane, mount, messages):
        nonlocal main_calls
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        main_calls += 1
        if main_calls == 1:
            tool_call = call('read', {'refs': ['conversations/one']})
            return Turn(
                tokens=4000,
                prompt_tokens=4000,
                completion_tokens=0,
                cached_tokens=None,
                tool_calls=(tool_call,),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
            )
        return Turn(tokens=4000, prompt_tokens=4000, completion_tokens=0, cached_tokens=None)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert main_calls == 2
    assert report['tokens'] == report['price_weighted_tokens'] == 8000
